# TAME

**TAME Arranges My Errands.** A small, fast to-do list for your terminal: add a task in one
line, see what matters most, tick it off, move on.

```text
> tk add Call the bank +phone due:fri pri:H
Created task 1.
> tk add Water the plants project:home
Created task 2.
> tk
ID   Age   Project   Tags    Pri   Due          Description         Urg
───────────────────────────────────────────────────────────────────────
 1    5s             phone   H     2026-11-20   Call the bank      15.8
 2    3s   home                                 Water the plants    1.0
> tk 1 done
Completed task 1 'Call the bank'.
```

- **Quick to type**: `tk` lists your tasks, `tk 3 done` completes one, commands shorten
  (`tk mod`), and dates speak plain English: `due:fri`, `due:eom`, `due:+2w`.
- **Most urgent first**: priority, due date, age, tags and project add up to an
  [urgency](urgency.md) score, so the top of the list is what to do now.
- **Forgiving**: `tk undo` reverts any change, bulk changes ask first, deleted tasks are kept.
- **Windows first**, at home on Linux too. English or French interface.
- **A little love**: now and then, TAME reminds you of the people around you
  ([kind words](settings.md#kind-words)). Need one right now? `tk love`. ♥
- **Taskwarrior-friendly**: same grammar spirit, and its JSON
  [imports and exports](taskwarrior.md) both ways.

## Install

On Windows, in PowerShell (no Python needed, see [Installation for beginners](install-beginners.md)):

```powershell
irm https://skitourer.github.io/tame/install.ps1 | iex
```

Already using [uv](https://docs.astral.sh/uv/)?

```sh
uv tool install tame-tasks
```

This installs two commands, `tame` and its short alias `tk`. Then follow
[Getting started](getting-started.md), or run `tk help tour` for the two-minute tour.

## Where to go next

| Page | What you'll find |
|---|---|
| [Installation for beginners](install-beginners.md) | step by step, nothing to know beforehand |
| [Getting started](getting-started.md) | first tasks, the everyday commands |
| [Commands](commands.md) | every command, with examples |
| [Filters & grammar](grammar.md) | how a command line is read, filters, dates |
| [Urgency](urgency.md) | how tasks are ranked |
| [Settings](settings.md) | `config.toml` and `tk config` |
| [Coming from Taskwarrior](taskwarrior.md) | import, export, the `task` alias, differences |
| [Credits & licenses](credits.md) | who made it, with what, under which licenses |
| [Specification](SPEC.md) | the full V1 specification |
