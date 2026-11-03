## vcpkg_setup - Goal

The vcpkg-configuration.json and the CMakePresets.json are common across all ManiVaultStudio repos.
Refer to the README.md in build_matrices for instructions on extending the the presets
and build matrices.

If an overriding version of these files is not found in the the repo these default versions will
be copied from here. 

Note that vcpkg-configuration.json must have the baselines maintained to produce controlled builds. 
This means that releases will be liked to a specific commit of github-actions.