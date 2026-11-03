## Reusable composite action for hdps core or plugin build with Conan
This action supportss Linux or macOS

### conan_build_linuxmac Inputs
```
inputs:
  conan-compiler:
    description: 'gcc apple-clang'
    required: true
  conan-cc:
    description: 'gcc clang'
    required: true
  conan-cxx:
    description: 'g++ clang++'
    required: true
  conan-compiler-version:
    description: 'A number [gcc: 8 9 10 11 12 14] [clang: 39 40 50 60 7 8 9 10 11 12 13 14 15 16 17 18 19 20] [10.0]'
    required: true
  conan-libcxx-version:
    description: 'Linux: libstdc++ or Macos: libc++ '
    required: true
  conan-build-type:
    description: 'Debug or Release'
    required: true
  conan-build-os:
    description: 'Linux or Macos'
    required: true
  conan-user:
    description: 'pass secrets.LKEB_ARTIFACTORY_USER'
    required: true
  conan-password:
    description: 'pass secrets.LKEB_ARTIFACTORY_PASSWORD'
    required: true
  conan-pem:
    description: 'pass secrets.LKEB_CERT_CHAIN'
    required: true
```