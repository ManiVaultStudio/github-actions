## Reusable composite action for hdps core or plugin build with Conan
This action supports Windows(2016)

Initial testing for Windows(2019) suggests that the chocolatey install of openssh could be skipped.

### conan_build_windowsc Inputs

```
  conan-visual-version:
    description: 'MSVC version: 16, 17 represent msvc-2019 and msvc-2022'
    required: true
  conan-visual-runtime:
    description: 'MD or MDd'
    required: true
  conan-build-type:
    description: 'Debug or Release'
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
  rs_ssh_key:
    description: 'pass secrets.RULESSUPPORT_DEPLOY_KEY'
    required: true
```