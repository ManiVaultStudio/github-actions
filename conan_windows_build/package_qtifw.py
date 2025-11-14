#!/usr/bin/env python3
import argparse, json, os, shutil, sys, tempfile, subprocess
from pathlib import Path
import requests
from datetime import date
import urllib3

# silence HTTPS verify warnings (you requested verify=False)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------
# Basic helpers
# ---------------------------
def print_indented(text, indent_level=1, spaces_per_level=4):
    prefix = " " * (indent_level * spaces_per_level)

    print("".join(
        prefix + line if line.strip() else line
        for line in text.splitlines(keepends=True)
    ))

def sha1_of_file(p: Path) -> str:
    import hashlib
    h = hashlib.sha1()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

def mk_package_xml(dst: Path, meta):
    dst.write_text(f"""<Package>
  <Name>{meta["id"]}</Name>
  <DisplayName>{meta["name"]}</DisplayName>
  <Description>{meta["description"]}</Description>
  <Version>{ meta["version"] }</Version>
  <ReleaseDate>{meta["release_date"]}</ReleaseDate>
</Package>
""", encoding="utf-8")

    # <Dependencies>Com.BioVault.CSV.Plugins</Dependencies>
def copy_payload(src_dir: Path, dst_dir: Path):
    dst_dir.mkdir(parents=True, exist_ok=True)
    if not src_dir.exists():
        raise FileNotFoundError(f"payload directory not found: {src_dir}")
    for root, _, files in os.walk(src_dir):
        r = Path(root)
        for fn in files:
            src = r / fn
            rel = src.relative_to(src_dir)
            out = dst_dir / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out)

# ---------------------------
# Artifactory HTTP helpers
# ---------------------------

def art_url(base_url, path):
    return f"{base_url.rstrip('/')}/artifactory/{path.lstrip('/')}"

def art_api_url(base_url, path):
    return f"{base_url.rstrip('/')}/artifactory/api/{path.lstrip('/')}"

def art_upload_file(session, base_url, repo, repo_path, local_path):
    """Try checksum deploy (fast if duplicate), else fall back to normal PUT."""
    p = Path(local_path)
    url = art_url(base_url, f"{repo}/{repo_path.lstrip('/')}")
    # 1) checksum-only deploy (no body)
    sha1 = sha1_of_file(p)
    r = session.put(url, headers={"X-Checksum-Deploy": "true", "X-Checksum-Sha1": sha1}, verify=False)
    if r.status_code in (200, 201):
        return
    # 2) normal upload with body
    with p.open('rb') as f:
        r = session.put(url, data=f, verify=False)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Upload failed [{r.status_code}] {url} -> {r.text[:300]}")

def art_upload_tree(session: requests.Session, base_url: str, repo: str, base_remote_path: str, local_root: Path, upload_updates_last: bool=False):
    """Upload a tree; when upload_updates_last=True, upload Updates.xml last for quasi-atomic switch."""
    files = []
    for p in local_root.rglob("*"):
        if p.is_file():
            rel = p.relative_to(local_root).as_posix()
            files.append((rel, p))

    if upload_updates_last:
        # push everything except Updates.xml first
        head = [(rel, p) for rel, p in files if not rel.endswith("Updates.xml")]
        tail = [(rel, p) for rel, p in files if rel.endswith("Updates.xml")]
        order = head + tail
    else:
        order = files

    for rel, p in order:
        art_upload_file(session, base_url, repo, f"{base_remote_path.rstrip('/')}/{rel}", p)

# ---------- OSS-safe listing & download (recursive via /api/storage) ----------

def art_folder_info(session, base_url, repo, remote_path):
    url = art_api_url(base_url, f"storage/{repo}/{remote_path.strip('/')}")
    r = session.get(url, verify=False)
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise RuntimeError(f"Folder info failed [{r.status_code}] {url} -> {r.text[:200]}")
    return r.json()

def art_download_tree_recursive(session, base_url, repo, remote_path, local_root):
    info = art_folder_info(session, base_url, repo, remote_path)
    if not info:
        return
    children = info.get("children", [])
    local_root.mkdir(parents=True, exist_ok=True)
    for child in children:
        name = child.get("uri", "").lstrip("/")
        if not name:
            continue
        child_remote = f"{remote_path.strip('/')}/{name}"
        child_local = local_root / name
        if child.get("folder"):
            art_download_tree_recursive(session, base_url, repo, child_remote, child_local)
        else:
            file_url = art_url(base_url, f"{repo}/{child_remote}")
            rf = session.get(file_url, stream=True, verify=False)
            if rf.status_code == 200:
                child_local.parent.mkdir(parents=True, exist_ok=True)
                with child_local.open("wb") as f:
                    for chunk in rf.iter_content(chunk_size=1024*1024):
                        if chunk:
                            f.write(chunk)
            elif rf.status_code != 404:
                raise RuntimeError(f"Download failed [{rf.status_code}] {file_url} -> {rf.text[:200]}")

def art_download_repo_current(session: requests.Session, base_url: str, repo: str, remote_path: str, local_out: Path):
    """Download repo-current recursively (OSS-safe, no ?list&deep)."""
    remote_path = remote_path.strip("/")
    art_download_tree_recursive(session, base_url, repo, remote_path, local_out)

def art_delete_path(session: requests.Session, base_url: str, repo: str, remote_path: str):
    url = art_url(base_url, f"{repo}/{remote_path.strip('/')}")
    r = session.delete(url, verify=False)
    if r.status_code in (200, 202, 204, 404):
        return
    raise RuntimeError(f"Delete failed [{r.status_code}] {url} -> {r.text[:200]}")

def main():
    try:
        ap = argparse.ArgumentParser(description="Build & upload Qt IFW component(s), update IFW repo(s), and publish to repo-current (OSS-safe)")
        
        ap.add_argument("--work-dir", required=True, help="Working directory")
        ap.add_argument("--branch", required=True, help="Branch name")
        ap.add_argument("--os", required=True, choices=["windows","macos","linux"], help="Target OS key (used in pathing)")
        ap.add_argument("--art-url", required=True, help="Base Artifactory URL, e.g. https://artifactory.example.com")
        ap.add_argument("--art-repo", required=True, help="Artifactory repository name, e.g. releases or generic-repo")
        ap.add_argument("--art-base", required=True, help="Base path under repo, e.g. ifw (will append /<os-short>/...)")
        ap.add_argument("--art-user",  default=os.getenv("ARTIFACTORY_USER"))
        ap.add_argument("--art-password",  default=os.getenv("ARTIFACTORY_PASSWORD"))
        
        args = ap.parse_args()

        branch = args.branch

        if not branch.startswith("release/"):
            raise RuntimeError("Only release/* branches are supported", file=sys.stderr)

        is_core_release = branch.startswith("release") and branch.count("/") == 1

        print_indented(str(is_core_release), 1)

        session = requests.Session()
        
        if args.art_user and args.art_password:
            session.auth = (args.art_user, args.art_password)

        branch_segments         = branch.split("/")
        app_version             = branch_segments[1] if is_core_release else branch_segments[1].replace("core_", "")
        app_version_internal    = app_version.replace(" ", "")

        print(f"Packaging parameters:")
        print(f"Artifactory URL:    {args.art_url}")
        print(f"Artifactory repo:   {args.art_repo}")
        print(f"Artifactory base:   {args.art_base}")
        print(f"Is core release:    {is_core_release}")
        print(f"Work dir:           {args.work_dir}")
        print(f"Branch:             {branch}")
        print(f"OS:                 {args.os}")
        print(f"App version:        {app_version}")
        print(f"App version (int):  {app_version_internal}")

        work_dir        = args.work_dir if args.work_dir is None else args.work_dir
        temporary_dir   = tempfile.TemporaryDirectory()
        temp_dir        = Path(temporary_dir.name)
                
        packaging_recipe_file_path = Path(work_dir, ".packaging", "recipe.json")

        if not packaging_recipe_file_path.exists():
            raise RuntimeError(f"Packaging recipe not found at { packaging_recipe_file_path }")
        
        packaging_recipe = json.loads(packaging_recipe_file_path.read_text(encoding="utf-8"))

        if not "inputs" in packaging_recipe:
            raise RuntimeError(f"Packaging recipe missing inputs field", file=sys.stderr)
        
        inputs                      = packaging_recipe["inputs"]
        plugin_info_json_file_name  = "PluginInfo.json"

        for input in inputs:
            if not "dir" in input:
                raise RuntimeError(f"Input missing dir field", file=sys.stderr)
            
            if not "postfix" in input:
                raise RuntimeError(f"Input missing postfix field", file=sys.stderr)

            input_dir           = Path(work_dir, input["dir"])
            post_fix            = input["postfix"]
            package_id          = f"Com.BioVault.{ str(app_version).title() }{ f'.{post_fix}' if post_fix else '' }"
            package_name        = input.get("name", package_id)
            plugin_info_path    = None if is_core_release else Path(work_dir, input_dir, plugin_info_json_file_name)
            
            if plugin_info_path is not None and not plugin_info_path.exists():
                raise RuntimeError(f"{ plugin_info_path } not found")

            print_indented(f"Processing input: { input_dir } with postfix { post_fix }", 1)
            print_indented(f"Input dir:        { input_dir }", 2)
            print_indented(f"Package id:       { package_id }", 2)
            print_indented(f"Package name:     { package_name }", 2)
            print_indented(f"Plugin info path: { plugin_info_path }", 2)

            if not is_core_release:
                plugin_info = json.loads(plugin_info_path.read_text(encoding="utf-8"))
                
                if not "name" in plugin_info:
                    raise RuntimeError(f"{ plugin_info_path } missing name field", file=sys.stderr)
                
                if not "version" in plugin_info:
                    raise RuntimeError(f"{ plugin_info_path } missing version field", file=sys.stderr)
                
                if not "plugin" in plugin_info["version"]:
                    raise RuntimeError(f"{ plugin_info_path } missing version.plugin field", file=sys.stderr)

                if not "core" in plugin_info["version"]:
                    raise RuntimeError(f"{ plugin_info_path } missing version.core field", file=sys.stderr)
                
                plugin_description  = plugin_info.get("description", "undefined")
                plugin_version      = plugin_info["version"]["plugin"]
            
            packages_root   = Path(temp_dir, "packages")
            package_root    = Path(packages_root, package_id)

            if package_root.exists():
                shutil.rmtree(package_root)
            
            print_indented(f"1. Preparing package root at { package_root }", 3)
            meta_dir = Path(package_root, "meta")
            data_dir = Path(package_root, "data")

            meta_dir.mkdir(parents=True, exist_ok=True)
            data_dir.mkdir(parents=True, exist_ok=True)
            
            mk_package_xml(meta_dir / "package.xml", {
                "id": package_id,
                "name": package_name,
                "version": "1.0" if is_core_release else plugin_version,
                "description": app_version if is_core_release else plugin_description,
                "release_date": date.today().isoformat(),
            })

            art_base            = Path(args.os, app_version_internal).as_posix()
            remote_repo_current = Path(art_base, "repo-current").as_posix()
            local_repo          = Path(temp_dir, f"repo-{ args.os }-{ app_version_internal }")
            remote_component    = f"{ art_base }/packages/{ package_id }"

            print_indented(f"2. Uploading component to Artifactory at { args.art_url }/{ args.art_repo }/{ remote_component }", 3)
            art_upload_tree(session, args.art_url, args.art_repo, remote_component, package_root)

            print_indented(f"3. Downloading { art_base }/current-repo from Artifactory", 3)
            art_download_repo_current(session, args.art_url, args.art_repo, remote_repo_current, local_repo)

            print_indented("4. Updating downloaded current-repo with new package...", 3)
            result = subprocess.run(["repogen", "--update", "-p", str(packages_root.absolute()), str(local_repo)])
            
            if result.returncode != 0:
                raise RuntimeError(f"Unable to re-generate package repository ")

            print_indented("5. Uploading updated current-repo to Artifactory", 3)
            art_upload_tree(session, args.art_url, args.art_repo, remote_repo_current, local_repo, upload_updates_last=True)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
