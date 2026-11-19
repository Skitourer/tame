# TAME

**TAME Arranges My Errands** — a lightweight, Taskwarrior-inspired command-line task manager,
Windows 11 first.

> Status: pre-alpha. Only `tame version` works for now; see the roadmap in
> [docs/SPEC.md](docs/SPEC.md#8-layout-quality-release).

TAME is an independent project. It shares no code, name or logo with Taskwarrior; it only aims
for compatibility with Taskwarrior's JSON import/export format.

## Install

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv tool install git+https://github.com/skitourer/tame
```

This installs two commands: `tame` and its short alias `tk`.

## Usage

```sh
tk version
```

Planned V1 commands: `add list done delete modify info undo export import help version alias`.
See [docs/SPEC.md](docs/SPEC.md) for the full specification.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
