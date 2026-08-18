Resolves the local configuenvration file created by `init-local-config`.

## Notes

Its stdout is consumed by command substitution inside `config_setup.sh`:

```bash
local_config_file=$(mgsnake get-local-env-path)
```

so the command prints the path and nothing else. Diagnostics go to stderr precisely so this stays
parseable at any log level.
