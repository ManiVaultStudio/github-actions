import argparse
import importlib 
import os
import sys
from pathlib import Path
from subprocess import run

def get_list_from_conanfile(args):
    # the information is in the conanfile if that file
    # contains a compatibility function
    root_path = Path(os.getenv("GITHUB_WORKSPACE", "."))
    import_path = root_path.parents[0]
    print(f"import path {import_path}")
    import_mod = root_path.parts[-1]
    print(f"import mod {import_mod}")
    sys.path.append(import_path)
    module = importlib.import_module(import_mod, package=None)
    print(f"{dir(module)}")
    if "compatibility" in dir(module):
        return (module.compatibility(args.os, args.compiler, args.compiler_version))
    return None



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("os", type=str, help="The os target of the build")
    parser.add_argument("compiler", type=str, help="The compiler target of the build")
    parser.add_argument("compiler_version", type=str, help="The compiler-version target of the build")
    args = parser.parse_args()
    list = get_list_from_conanfile(args)
    if list:
        run(['conan', 'profile', 'new', 'compatibility' ])
        for line in list:
            run(['conan', 'profile', 'update', f'settings.{line}', 'compatibility'])
