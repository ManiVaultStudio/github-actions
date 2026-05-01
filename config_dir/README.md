## config_dir

Conan profiles are based on jinja templates that can be filled with parameter settings
This replaces the `conan profile` commands in conan v1

## Profile differences and similarities Windows, Linux Macos

The Macos and Linux profiles contain identical settings but thethere is a difference with the Windows profile.

Windows has settings compiler.runtime (dynamic) and compiler.runtime_type (Release/Debug/RelWithDebInfo) whereas Macos and Linux have a compiler.libcxx settings.

Because of this Macos and Linux can same the profile template which is pobulated using vars derived from the build matrix.