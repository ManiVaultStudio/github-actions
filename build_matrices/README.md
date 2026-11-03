## Build matrices

The build matrices return a build image name and preset name. 
The preset name corresponds to one of the presets in 
`vcpkg_setup/CMakePresets.json`.

For macos matrix there is an extra entry that specifies the xcode version.

When extending the build matrix remember to supply both the matrix file 
and the extra contents in `vcpkg_setup/CMakePresets.json` 

