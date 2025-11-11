#!/usr/bin/env python3
import argparse, json, os, shutil, sys, tempfile, hashlib
from pathlib import Path
import requests
from datetime import date

def sha1_of_file(p: Path) -> str:
    h = hashlib.sha1()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

def mk_package_xml(dst: Path, meta):
    dst.write_text(f"""<Package>
  <Name>{meta["id"]}</Name>
  <DisplayName>{meta["name"]}</DisplayName>
  <Description>{meta["desc"]}</Description>
  <Version>{meta["version"]}</Version>
  <ReleaseDate>{meta["rd"]}</ReleaseDate>
  <Dependencies>org.manivault.core->={meta["minCore"]}</Dependencies>
</Package>
""", encoding="utf-8")

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

def art_upload_file(session: requests.Session, base_url: str, repo: str, repo_path: str, local: Path):
    """Upload a file to Artifactory using checksum deploy for idempotency."""
    sha1 = sha1_of_file(local)
    # Ensure forward slashes
    repo_path = repo_path.strip("/")

    url = f"{base_url.rstrip('/')}/artifactory/{repo}/{repo_path}"
    headers = {
        "X-Checksum-Deploy": "true",
        "X-Checksum-Sha1": sha1
    }
    with local.open('rb') as f:
        # When checksum matches an existing file, Artifactory will fast-complete upload without sending the body.
        resp = session.put(url, data=f, headers=headers)
    if resp.status_code not in (200,201):
        raise RuntimeError(f"Upload failed [{resp.status_code}] {url} -> {resp.text[:300]}")

def art_upload_tree(session: requests.Session, base_url: str, repo: str, base_remote_path: str, local_root: Path):
    for p in local_root.rglob("*"):
        if p.is_file():
            rel = p.relative_to(local_root).as_posix()
            art_upload_file(session, base_url, repo, f"{base_remote_path.rstrip('/')}/{rel}", p)

def main():
    ap = argparse.ArgumentParser(description="Build & upload a Qt IFW component to Artifactory")
    ap.add_argument("--plugin-json", required=True, help="Path to plugin.json")
    ap.add_argument("--payload", required=True, help="Directory with built files to put into data/")
    ap.add_argument("--os-short", required=True, choices=["win","macos","linux"], help="Target OS key used in pathing")
    ap.add_argument("--workdir", default=None, help="Working dir (default: temp)")
    ap.add_argument("--art-url", required=True, help="Base Artifactory URL, e.g. https://artifactory.example.com")
    ap.add_argument("--art-repo", required=True, help="Artifactory repository name, e.g. generic-repo")
    ap.add_argument("--art-base-path", required=True, help="Base path inside repo, e.g. ifw/win")
    # Auth: prefer token; fallback to user/pass
    ap.add_argument("--art-token", default=os.getenv("ARTIFACTORY_TOKEN"))
    ap.add_argument("--art-user",  default=os.getenv("ARTIFACTORY_USER"))
    ap.add_argument("--art-pass",  default=os.getenv("ARTIFACTORY_PASSWORD"))
    args = ap.parse_args()

    pj = json.loads(Path(args.plugin_json).read_text(encoding="utf-8"))
    meta = {
        "id": pj["id"],
        "version": pj["version"],
        "minCore": pj.get("minCoreVersion","0.0.0"),
        "name": pj.get("displayName", pj["id"]),
        "desc": pj.get("description",""),
        "rd": date.today().isoformat()
    }

    tmp = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="ifw_pub_"))
    packages_root = tmp / f"packages-{args.os_short}"
    comp_root = packages_root / meta["id"]
    meta_dir = comp_root / "meta"
    data_dir = comp_root / "data"

    meta_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    mk_package_xml(meta_dir / "package.xml", meta)
    copy_payload(Path(args.payload), data_dir)

    # Upload to Artifactory: <repo>/<base>/packages/<id>/{meta,data,...}
    remote_base = f"{args.art_base_path.strip('/')}/packages/{meta['id']}"
    s = requests.Session()
    if args.art_token:
        s.headers.update({"Authorization": f"Bearer {args.art_token}"})
    elif args.art_user and args.art_pass:
        s.auth = (args.art_user, args.art_pass)
    else:
        print("ERROR: provide --art-token or (--art-user & --art-pass)", file=sys.stderr)
        sys.exit(2)

    print(f"Uploading component to {args.art_url}/artifactory/{args.art_repo}/{remote_base}/ ...")
    art_upload_tree(s, args.art_url, args.art_repo, remote_base, comp_root)
    print("Upload complete ✅")
    print(f"Component ID: {meta['id']}")
    print(f"Version:      {meta['version']}")
    print(f"Min core:     {meta['minCore']}")
    print(f"Remote base:  {args.art_repo}/{remote_base}")

if __name__ == "__main__":
    main()

