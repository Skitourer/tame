# Security policy

## Supported versions

Only the latest release on [PyPI](https://pypi.org/project/tame-tasks/) gets fixes. Upgrade
with `uv tool upgrade tame-tasks`.

## Reporting a vulnerability

Please report it privately, not in a public issue: on GitHub, open the
[Security tab](https://github.com/Skitourer/tame/security) and click **Report a
vulnerability**. Describe what you found, how to reproduce it and the version
(`tk version`).

You get an answer within a week. Once a fix is released, the advisory is published with
credit to you, unless you prefer otherwise.

## Scope

TAME is a local command-line tool: it reads and writes your task database and settings in
your data folder, and, only when you turn on `completion`, a marked block in your shell
profile. Issues in these areas, in the release pipeline (GitHub Actions, PyPI publishing) or
in the installers (`install.ps1`, `install.sh`) are in scope.
