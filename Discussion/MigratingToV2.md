## The future of ManiVault build infrastructure: CI, devbundle, conan

### State of play

Currently the ManiVault build infrastructure is based on the following software:

* Binary artifact cache : Artifactory at lkeb-artifactory.lumc.nl
* Dependency management: 
  - CI tooling - conan v1.66, Desktop tooling 
  - InstallArtifactoryPackage.cmake desktop 
  - rulessupport python package that implements the branch naming rules for binary artifact retrieval
* CI: GitHub CI using GitHub images
* User tools: CMake, devbundle

### The need for change

A number of issues have arisen with the current system:

1. Old Conan: Conan will not be updated from 1.66 and so does not support changes to both the IDEs (Visual Studio, Xcode) or to CMake. We need to move to conan V2 (2.28 at time of writing)

2. Divergent dependency handling: Initially 3rd party dependencies were added to Artifactory by adding a conan-<package_name> to the biovault organisation. This proved difficult to maintain (lack or time or problematic builds) and as a result we see the following systems in the repos: 
    - submodules
    - CPM.cmake and or FetchContent
    - vcpkg

    While these are perfectly good solutions the variety of approaches does add to the overall complexity of the code base. 


4. Conan complexity. Our approach to binary artifacts is that the artifact should match a CMake export structure. That means that multiple release binaries (e.g. Debug, Release, RelWithDebInfo) can be included in a single package. We achieve this by overriding the build and package methods in the conanfile.py to ensure that multiple builds happen and are placed in a single package. This is contrary to the conan package model that expects one build type per package. 

5. Conan on CI but not on desktop. There are effectively two separate build systems tht have to be maintained.

6. Future personeel changes. Much of the accumulted knowledge regarding maintenance (especially of the conan builds) will leave the project in the foreseeable future.

### What works well

There are a number of features of the current system which successfully diliver important functionality to both the CI and desktop builds.

1. CI acceleration through binary caching 
2. Branch matching for new core/plugin paired feature development
3. Local build simplifictation through binary caching
4. DevBundle for creation of functional local build configurations



### Options

Going forward we need to replace **conan v1**. The questions is do we do a migration to **conan v2** or to alternative package management systems, specifically **vcpkg**

#### conan v2

Although our recipies (conanfile.py) have been kep uptodate with the latest conan generator systems (including CMake toolchain support) there are a numbe of issues:

1. For the migration the system does have to be substantially rewritten. 
  - build profiles are constructed via jinja templates
  - the binaries must be in a new artifactory repo 
  - the addition of build revision in conan package ID is not useful for us and is awkward to work around

#### vcpkg


### A comparable project

The blog from "Declaration of Var" documents the progress of a complex, multi-developer C++ project with major 3rd party dependencies and internal repo dependencies. See [Managing dependencies in a C++ project with vcpkg](https://decovar.dev/blog/2022/10/30/cpp-dependencies-with-vcpkg). 

As the blog name suggests this project settled on a vcpkg solution though conan v1 and v2 were considered. The work needed to get conan working in their build environment was [judged to be prohibitive](https://decovar.dev/blog/2022/10/30/cpp-dependencies-with-vcpkg/#an-update-after-a-second-attempt). 

It seems that vcpkg combined with a team/CI-wide binary cache results in a [performant build infrastructure](https://decovar.dev/blog/2022/10/30/cpp-dependencies-with-vcpkg/#2024-10-11--caching-in-jfrog-artifactory) 

However there will be other issues with vck pkg

1. [How to achieve dynamic versioning](Dynamic-versioning-with-vcpkg). Requirements are baked into the vcpkg.json file.  

#### Dynamic versioning with vcpkg

In conan overriding the **requirements()** function allowed us to dynamically version the core according to the branch naming rules (or for that matter any other ManiVault internal repo dependency). 

Possibilities: 

1. In vckpkg we need some kind of wrapper script, in python or CMake that can generate/modify the vcpkg.json from a template before triggering the build. Such a template might look like this.

```
{
  "name": "MyPlugin",
  "version-semver": "1.0.0",
  "dependencies": [
    { "name": "core", "version=": "@branch_version@" },
    { "name": "MyDataPlugin", "version=": "@branch_version" },
    { "name": "fmt", }
  ],
  "builtin-baseline":"aaaaannnn"
}
```

2. Alternatively an overlay-ports directory could be used with generating entries. (commandline )  

3. Or possible adding overrides to the vcpkg.json is the best option.

**Integration into existing tooling** 
Possibly these functions could be integrated with a ManiVault DevBundle v2 tool. A future version of DevBundle could be say uv installable and come with a number of vcpkg helper subcommand. 




