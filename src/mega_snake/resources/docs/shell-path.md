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

Sourcing that script sets `MEGA_SNAKE_SHELL` and defines `mgsnake_reload`, `mgsnake_load_env` and
`mgsnake_reload_all`. Because the profile calls this command *before* that variable exists, it is
the one command that runs with no initialization at all — which is also why it prints the bare path
and nothing else.

It also defines `mgsnake` itself as a thin shell function around the real executable. That function
is what makes the environment auto-reload work: a command that rewrites one of the local environment
files exits with status `29`, and only the parent shell can act on it — a child process cannot
change its parent's environment. The function forwards every argument, returns the real status, and
calls the executable through `command mgsnake` (or its resolved path on PowerShell), so there is no
recursion. The only visible difference is that `type mgsnake` reports a function.
