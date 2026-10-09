import os
import subprocess
import tomllib
import shutil
from pathlib import Path

print("Building ManiVault dependencies overlay")
workspace = Path(os.getenv("GITHUB_WORKSPACE", "."))
# Load TOML dependencies
toml_file = Path(workspace, "mv_deps.toml")
if not toml_file.exists():
    print("No mv_deps.toml found, skipping dynamic submodule setup.")
    exit(0)

with open(toml_file, "rb") as f:
    deps = tomllib.load(f)

# Get current branch of the consumer repo
# In PRs, use GITHUB_HEAD_REF; on push, use GITHUB_REF_NAME
consumer_branch = os.getenv("GITHUB_HEAD_REF") or os.getenv("GITHUB_REF_NAME", "main")
print(f"Consumer active branch: {consumer_branch}")

template_port = Path(workspace, ".github/templates/portfile.cmake")

for key, config in deps.items():
    repo = config["repo"]
    package_name = config.get("package", key)
    ref = config.get("ref", "main")
    match_branch = config.get("match_branch", False)

    # Determine target branch
    target_branch = ref
    if match_branch:
        # Check if target branch exists on remote repository
        ls_remote = subprocess.run(
            ["git", "ls-remote", "--heads", f"https://github.com/{repo}.git", consumer_branch],
            capture_output=True, text=True
        )
        if ls_remote.returncode == 0 and consumer_branch in ls_remote.stdout:
            target_branch = consumer_branch
            print(f"[{package_name}] Branch match found! Using: {target_branch}")
        else:
            print(f"[{package_name}] Branch '{consumer_branch}' not found on remote. Falling back to: {target_branch}")

    submodule_dir = Path("external") / package_name
    port_dir = Path("ports") / package_name

    # 1. Add submodule if not present
    if not submodule_dir.exists():
        repo_url = f"https://github.com/{repo}.git"
        print(f"Adding submodule {package_name} (branch: {target_branch})...")
        subprocess.run(
            ["git", "submodule", "add", "-b", target_branch, repo_url, str(submodule_dir)],
            check=True
        )
    
    # Ensure submodule is initialized and updated
    subprocess.run(["git", "submodule", "update", "--init", "--recursive", str(submodule_dir)], check=True)

    # 2. Inject overlay portfile into ports/<package_name>/portfile.cmake
    port_dir.mkdir(parents=True, exist_ok=True)
    target_portfile = port_dir / "portfile.cmake"
    shutil.copy(template_port, target_portfile)
    print(f"Injected portfile for {package_name} -> {target_portfile}")