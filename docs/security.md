# Data security

TAME does not encrypt your tasks. They are stored in a plain SQLite file, `tasks.db`, in the
data folder (`%APPDATA%\tame` on Windows, `~/.local/share/tame` on Linux). Files written by
`tk print --file` and `tk export` are plain too. Anyone who can read your files can read your
tasks. `tk help security` says the same in the terminal.

## Protect them with Windows

- **BitLocker** encrypts the whole disk. It is often already on for work computers: see
  *Settings > Privacy & security > Device encryption*.
- **EFS** encrypts a folder for your Windows account only. Run once:

    ```powershell
    cipher /e /s:"$env:APPDATA\tame"
    ```

    (`cipher /e /s:"%APPDATA%\tame"` in `cmd`). EFS is not available on Windows Home editions.

On Linux, use full-disk encryption (LUKS) or an encrypted home folder.

## Why TAME does not encrypt the file itself

- Python's `sqlite3` cannot read an encrypted database, and encrypted SQLite builds would add a
  native dependency.
- TAME would have to write a decrypted copy to disk while it works: your tasks would sit there in
  plain text, which defeats the purpose.
- It would ask for a password and derive a key at every command, which makes each `tk` slower.

An encrypted export, for backups and moving tasks between computers, is planned together with
sync (see the [roadmap](ROADMAP.md)).
