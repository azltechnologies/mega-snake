Outputs the initialization script path to configure the shell.

**For bash/zsh**, add this line to `~/.bashrc` or `~/.zshrc`:

```bash
. "$(mgsnake shell-path bash)"
```

**For PowerShell**, add this line to your PowerShell profile (usually `$PROFILE`):

```powershell
. (mgsnake shell-path pwsh)
```
