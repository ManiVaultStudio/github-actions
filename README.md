# common_actions
GitHub actions that can be reused in other hdps repos for CI or other purposes.

# Conan Version

Branches v2.x supports conan v2.x. 

## Why is this necessary?

At the time of creation (November 2020) GitHub does not have a built-in solution for centrally managed actions or workflow templates. It is an open item on the [Actions Roadmap](https://github.com/github/roadmap/issues/98).

Basic [workflow templates](https://docs.github.com/en/free-pro-team@latest/actions/learn-github-actions/sharing-workflows-with-your-organization) do exit but they only applied when creating a workflow for the first time.

For more information see [the background info section.](background-information-for-the-actions-system)

## Security
~~Malicious code in common actions could have serious consequences for the integrity of repo code.
For that reason this repository shall be kept readonly except for CI/CD maintainers. In this case follow
the [read-only usage example](common-actions-is-read-only). (Not this was changed from the original private
strategy it permits simpler application of the actions.)~~

Currently it is not possible to direct an action to a private repo.Consider using https://github.com/marketplace/actions/private-actions-checkout as an alternative to the [private option](common-actions-is-private) below

## Using common-actions

Centralize the common CI actions in one repository. Usage depends on the security approach adopted: either private or read-only.

### common-actions is read-only

With a read-only repo using the actions is reltively simple. Use as follows:

```yaml
- name: Checkout hdps/common_actions
  uses: hdps/common-actions/conan_windows_build@master
    ...

- name: Checkout hdps/common_actions
  uses: hdps/common-actions/conan_linuxmac_build@master
    ...
```

### common-actions is private
A more complex approach is needed: Clone the repository to the .github/common_actions directory of the repository being built in the CI. An SSH key could be used for the checkout [see the actions repo doc](https://github.com/actions/checkout). This requires the following boiler plate code:


```yaml
- uses: actions/checkout@v2
- name: Checkout hdps/common_actions
  uses: actions/checkout@v2
  with:
    repository: hdps/common_actions
    ref: refs/heads/master
    ssh-key: ${{ secrets.CA_SSH_PRIVATEKEY }}
    persist-credentials: false
    path: ./.github/common_actions

- uses: ./.github/common-actions/conan_windows_build
  with:
    ...
```
Versioning can be applied with the **ref** parameter to **actions/checkout@v2**


### Background information for the actions system
The approach was selected from various options (including one where updates to the central repo are pushed to consumer repos) and is based on the examples described in [Roque Pinel's blog](https://www.pinel.cc/blog/2019/11/02/private-github-actions). It has the disadvantage or advantage (depending on your use case) of not automatically triggering a new build when a central action changes

## Action naming conventions

The action is in the **action.yml** file under an action name directory. Place a README.md file there

e.g.
```
conan_linuxmac_build
  - action.yml
  - README.md
conan_windows_build
  - action.yml
  - README.md
```

## Issues

Due to a markup/jinja bug conan install is:

```
        pip install conan~=1.43.0
        pip install "markupsafe<2.1"
```

## Index

| Action directory     | Function                                                         | Inputs link                                          |
| -------------------- | ---------------------------------------------------------------- | ---------------------------------------------------- |
| conan_build_linuxmac | Install dependencies and execute a conan build on linux or mac   | [Linux Mac Inputs](./conan_linuxmac_build/README.md) |
| conan_build_windows  | Install dependencies and execute a conan build on Windows (2016) | [Windows Inputs](./conan_windows_build/README.md)    |



## Future

Migrate to GitHub centrally managed actions when they become available in 2021.
