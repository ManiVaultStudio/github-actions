## config_dir

Setup the 
## Profile differences and similarities Windows, Linux Macos

The Macos and Linux profiles contain identical settings but thethere is a difference with the WIndows profile.

WIndows has settings compiler.runtime (dynamic) and compiler.runtime_type (Release/Debug/RelWithDebInfo) whereas Macos and Linux have a compiler.libcxx settings.

Because of this Macos and Linux can same the profile template which is pobulated using vars derived from the build matrix.