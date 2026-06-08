### Function of conan_support

#### Usage

After a `cmake generate, build and install` run `conan create` giving the location prefix used for the `cmake install` thus:

```
CONAN_STAGE_DIR=<cmake_install_prefix_dir> conan create . --profile ci-release
```
Where the profile contains the compiler settings and option thatwere used in the build.

#### Prerequisites

The generic `conanfile.py` that can be use with the ManiVaultCore 
or any of the Plugins that respect the following

1. There is a source of version information. Either:
    - The branch as parsed according to the ManiVaultSTudio naming rules
    - A VERSION file
    - A PluginInfo.json file

2. Have a CMake file that can be used with the following sequence:
    - cmake generate
    - cmake build
    - cmake install


