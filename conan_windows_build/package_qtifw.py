#!/usr/bin/env python3
from email.mime import base
import argparse, json, os, shutil, sys, tempfile, hashlib, time, subprocess
from pathlib import Path
import requests
from datetime import date
import urllib3

# silence HTTPS verify warnings (you requested verify=False)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------
# Basic helpers
# ---------------------------

def run(cmd, cwd=None):
    print(f"+ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0:
        print(r.stdout)
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    return r.stdout

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
  <Version>1.0.1</Version>
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
        ap.add_argument("--workdir", default=None, help="Working dir (default: temp)")
        ap.add_argument("--art-url", required=True, help="Base Artifactory URL, e.g. https://artifactory.example.com")
        ap.add_argument("--art-repo", required=True, help="Artifactory repository name, e.g. releases or generic-repo")
        ap.add_argument("--art-base", required=True, help="Base path under repo, e.g. ifw (will append /<os-short>/...)")
        ap.add_argument("--art-user",  default=os.getenv("ARTIFACTORY_USER"))
        ap.add_argument("--art-password",  default=os.getenv("ARTIFACTORY_PASSWORD"))
        ap.add_argument("--repogen", default="repogen", help="Path to repogen (default: in PATH)")
        ap.add_argument("--build-id", default=None, help="Build id (unused now; kept for logs)")
        
        args = ap.parse_args()

        branch = args.branch

        if not branch.startswith("release/"):
            raise RuntimeError("Only release/* branches are supported", file=sys.stderr)

        is_core_release = branch.startswith("release") and branch.count("/") == 1

        print(is_core_release)

        session = requests.Session()
        
        if args.art_user and args.art_password:
            session.auth = (args.art_user, args.art_password)

        branch_segments         = branch.split("/")
        app_version             = branch_segments[1] if is_core_release else branch_segments[1].replace("core_", "")
        app_version_internal    = app_version.replace(" ", "")
        plugin_version          = "undefined" if is_core_release else branch_segments[2]

        print(f"""\n=== Parameters ===""")
        print(f"Artifactory URL:    {args.art_url}")
        print(f"Artifactory repo:   {args.art_repo}")
        print(f"Artifactory base:   {args.art_base}")
        print(f"Is core release:    {is_core_release}")
        print(f"Work dir:           {args.work_dir}")
        print(f"Branch:             {branch}")
        print(f"OS:                 {args.os}")
        print(f"App version:        {app_version}")
        print(f"App version (int):  {app_version_internal}")
        print(f"Plugin version:     {plugin_version}")

        work_dir        = args.work_dir if args.workdir is None else args.workdir
        temporary_dir   = tempfile.TemporaryDirectory()
        temp_dir        = Path(temporary_dir.name)
        packages_root   = Path(temp_dir, f"packages-{ plugin_version }")

        print(f"Using temp dir: { packages_root }")
        
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
            package_id          = f"Com.BioVault.{ str(app_version).title() }.{ post_fix }"
            package_name        = input.get("name", package_id)
            plugin_info_path    = Path(work_dir, input_dir, plugin_info_json_file_name)
            
            if not plugin_info_path.exists():
                raise RuntimeError(f"{ plugin_info_path } not found")

            print(f"\nProcessing input: { input_dir } with postfix { post_fix }")
            print(f"\tInput dir:        { input_dir }")
            print(f"\tPackage id:       { package_id }")
            print(f"\tPackage name:     { package_name }")
            print(f"\tPlugin info path: { plugin_info_path }")

            plugin_info = json.loads(plugin_info_path.read_text(encoding="utf-8"))
            
            if not "name" in plugin_info:
                raise RuntimeError(f"{ plugin_info_path } missing name field", file=sys.stderr)
            
            if not "version" in plugin_info:
                raise RuntimeError(f"{ plugin_info_path } missing version field", file=sys.stderr)
            
            if not "plugin" in plugin_info["version"]:
                raise RuntimeError(f"{ plugin_info_path } missing version.plugin field", file=sys.stderr)

            if not "core" in plugin_info["version"]:
                raise RuntimeError(f"{ plugin_info_path } missing version.core field", file=sys.stderr)
            
            plugin_name             = plugin_info["name"]
            plugin_description      = plugin_info.get("description", "undefined")
            plugin_version          = plugin_info["version"]["plugin"]
            plugin_core_versions    = plugin_info["version"]["core"]
            
            comp_root = Path(packages_root, package_id)
            
            if comp_root.exists():
                shutil.rmtree(comp_root)
            
            meta_dir = comp_root / "meta"
            data_dir = comp_root / "data"

            meta_dir.mkdir(parents=True, exist_ok=True)
            data_dir.mkdir(parents=True, exist_ok=True)
            
            mk_package_xml(meta_dir / "package.xml", {
                "id": package_id,
                "name": package_name,
                "version": plugin_version,
                "description": plugin_description,
                "release_date": date.today().isoformat(),
            })

            art_base            = Path(args.os, app_version_internal).as_posix()
            remote_repo_current = Path(art_base, "repo-current").as_posix()
            local_repo          = Path(temp_dir, f"repo-{ args.os }-{ app_version_internal }")
            remote_component    = f"{ art_base }/packages/{ package_id }"

            print(f"Uploading component to Artifactory at { args.art_url }/{ args.art_repo }/{ remote_component }")
            art_upload_tree(session, args.art_url, args.art_repo, remote_component, comp_root)

            print(f"\tDownloading { art_base }/current-repo from Artifactory")
            art_download_repo_current(session, args.art_url, args.art_repo, remote_repo_current, local_repo)
        
            print("\tUpdating downloaded current-repo with new package...")
            run([args.repogen, "--update", "-p", str(packages_root), str(local_repo)])

            print("\tUploading updated current-repo to Artifactory")
            art_upload_tree(session, args.art_url, args.art_repo, remote_repo_current, local_repo, upload_updates_last=True)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
