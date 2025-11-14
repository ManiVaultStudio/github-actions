import argparse, json, os, shutil, sys, tempfile, subprocess
from pathlib import Path
import requests
from datetime import date

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

def main():
    try:
        ap = argparse.ArgumentParser(description="Build & upload Qt IFW component(s), update IFW repo(s), and publish to repo-current (OSS-safe)")
        
        ap.add_argument("--app-name", required=True, help="Application name (used in package metadata)")
        ap.add_argument("--work-dir", required=True, help="Working directory")
        ap.add_argument("--os", required=True, choices=["windows","macos","linux"], help="Target OS key (used in pathing)")
        ap.add_argument("--art-url", required=True, help="Base Artifactory URL, e.g. https://artifactory.example.com")
        ap.add_argument("--art-repo", required=True, help="Artifactory repository name, e.g. releases or generic-repo")
        ap.add_argument("--art-base", required=True, help="Base path under repo, e.g. ifw (will append /<os-short>/...)")
        ap.add_argument("--art-user",  default=os.getenv("ARTIFACTORY_USER"))
        ap.add_argument("--art-password",  default=os.getenv("ARTIFACTORY_PASSWORD"))
        
        args    = ap.parse_args()
        session = requests.Session()
        
        if args.art_user and args.art_password:
            session.auth = (args.art_user, args.art_password)

        app_name                = args.app_name.replace(" ", "")
        work_dir                = args.work_dir if args.work_dir is None else args.work_dir
        temporary_dir           = tempfile.TemporaryDirectory()
        temp_dir                = Path(temporary_dir.name)
        art_base                = Path(args.os, app_name).as_posix()
        remote_packages         = Path(art_base, "packages").as_posix()
        local_packages          = Path(temp_dir, "packages")

        art_download_repo_current(session, args.art_url, args.art_repo, remote_packages, local_packages)
        run(["binarycreator", "-c", Path(work_dir, ".packaging", "config.xml").as_posix(), "-p", local_packages.as_posix(), Path("D:\\packaging").as_posix()])

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()