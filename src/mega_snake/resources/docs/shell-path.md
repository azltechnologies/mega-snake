Add the matching line to your shell profile — this is what makes `mgsnake` shell integration active
in every new session.

## Examples

For bash/zsh, in `~/.bashrc` or `~/.zshrc`:

```bash
. "$(mgsnake shell-path bash)"
```

For PowerShell, in your profile (`$PROFILE`):

```powershell
. (mgsnake shell-path pwsh)
```

## Notes

Sourcing that script sets `MEGA_SNAKE_SHELL` and defines `mgsnake_reload`. Because the profile calls
this command *before* that variable exists, it is the one command that runs with no initialization
at all — which is also why it prints the bare path and nothing else.
