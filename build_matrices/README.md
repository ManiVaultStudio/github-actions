# Note on build matrices - architectures, compiler versions etc.

Please document any significant changes to the build matrices here.

## Windows notes

#### MSVC Compiler version in conan

Moving from conan v1 to v2 the compiler version was changed from the Visual Studion IDE version i.e. 15, 16, 17 to the first three digits of _MSC_VER ([has the format MMNN](https://en.wikipedia.org/wiki/Microsoft_Visual_C%2B%2B#Internal_version_numbering) ). The correspondence is as follows:

Visual Studio version | Version Code | Conan compiler version(s) = first 3 digits _MSC_VER
---|---|---
2017 | 15.x | 191
2019 | 16.x | 192
2022 | 17.0->17.9 | 193
2022 | 17.10-> | 194

#### Architecture

All versions build on x86_64

## Linux notes

#### Architecture

All versions build on x86_64

## MacOS notes

#### Architecture

XCode 14 & 15 build on x86_64
XCode 16 upard build on arm8 