import argparse
import importlib 
import os
import sys
from pathlib import Path
from subprocess import run
from inspect import isfunction

def call_func(full_module_name, func_name, *argv):
    module = importlib.import_module(full_module_name, package=__name__)
    for attribute_name in dir(module):
        attribute = getattr(module, attribute_name)
        if isfunction(attribute) and attribute_name == func_name:
            attribute(*argv)
        else:
            return None

def get_list_from_conanfile(args):
    # the information is in the conanfile if that file
    # contains a compatibility function
    root_path = Path(os.getenv("GITHUB_WORKSPACE", "."))
    import_path = root_path.parents[0]
    print(f"import path {import_path}")
    print(f"working dir {Path(os.curdir).absolute()}")
    print(f"{os.listdir(os.curdir)}")
    call_func(f'.conanfile', 'compatibility', args.os, args.compiler, args.compiler_version)

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
