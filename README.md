# common_actions
GitHub actions that can be reused in other hdps repos for CI or other purposes.

## Why is this necessary

At the time of creation (November 2020) GitHub does not have a built-in solution for centrally managed actions or workflow templates. It is an open item on the [Actions Roadmap](https://github.com/github/roadmap/issues/98).

Basic [workflow templates](https://docs.github.com/en/free-pro-team@latest/actions/learn-github-actions/sharing-workflows-with-your-organization) do exit but they only applied when creating a workflow for the first time.

## This solution  

Centralize the common CI actions in one repository. Pull the repository to the .github/common_actions directory of the repository being buil in the CI. This requires the following boiler plate code:

```yaml
- uses: actions/checkout@v2
- name: Checkout hdps/common_actions
  uses: actions/checkout@v2
  with:
    repository: hdps/common_actions
    ref: refs/heads/master
    # GitHub's personal access token with read access to `hdps/common_actions`
    # Can be stored in organisation secrets
    token: $
    persist-credentials: false
    path: ./.github/common_actions
- uses: ./.github/common-actions/conan_windows_build
  with:
    ...
```  
Versioning can be applied with the **ref** parameter to **actions/checkout@v2**

The approach was selected from various options (including one where updates to the central repo are pushed to consumer repos) and is based on the examples described in [Roque Pinel's blog](https://www.pinel.cc/blog/2019/11/02/private-github-actions). It has the disadvantage or advantage (depending on your use case) of not automatically triggering a new build when a central action changes

## Conventions

The action is in the **action.yml** file under an action name directory.

e.g.
```
conan_linux_build
  - action.yml
conan_windows_build
  - action.yml
```

## Security
Malicious code in common actions could have serious consequences for the integrity of repo code. For that reason this repository shall be kept private.

## Future

Migrate to GitHub centrally managed actions when they become available in 2021.
