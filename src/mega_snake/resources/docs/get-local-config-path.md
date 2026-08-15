Resolves the local configuration file created by `init-local-config`, picking the `.sh` or `.ps1`
variant according to the active shell.

## Notes

Its stdout is consumed by command substitution inside `config_setup.sh`:

```bash
local_config_file=$(mgsnake get-local-config-path)
```

so the command prints the path and nothing else. Diagnostics go to stderr precisely so this stays
parseable at any log level.
