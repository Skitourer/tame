# Installation for beginners

No need to know Python, or to install it: the installer takes care of everything. It takes
about a minute.

## Windows

1. Open **PowerShell**: press the ++windows++ key, type `powershell`, press ++enter++.
2. Copy this line, paste it in the PowerShell window (right-click pastes), press ++enter++:

    ```powershell
    irm https://skitourer.github.io/tame/install.ps1 | iex
    ```

3. When it says **Done!**, close the window and open a new PowerShell.
4. Type `tk` and press ++enter++. TAME greets you and shows what to try first.

## Linux

1. Open a terminal.
2. Run:

    ```sh
    curl -LsSf https://skitourer.github.io/tame/install.sh | sh
    ```

3. Open a new terminal and type `tk`.

## What the installer does

1. If [uv](https://docs.astral.sh/uv/) is missing, it installs it with uv's official
   installer. uv is a small tool that installs Python programs, and the Python they need, in
   your user folder. Nothing is installed system-wide, no administrator rights are needed.
2. It installs TAME with uv: the `tame` and `tk` commands.
3. If needed, it adds the folder of these commands to your `PATH`, so the terminal finds them.

You can read the scripts first: [install.ps1](install.ps1), [install.sh](install.sh).

## Update, uninstall

Run the same line again to update TAME. To remove it:

```sh
uv tool uninstall tame-tasks
```

Your tasks stay in their folder (see [Getting started](getting-started.md#where-is-my-data)).

## If it does not work

- **"running scripts is disabled on this system"** or a blocked download: your computer's
  policy forbids installers like this one. Install by hand instead, in two commands:

    ```powershell
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    uv tool install git+https://github.com/skitourer/tame
    ```

- **`tk` is not recognized**: open a *new* terminal; the `PATH` change only applies to
  terminals opened after the installation.
- Still stuck? [Open an issue](https://github.com/Skitourer/tame/issues) with the message you
  see.
