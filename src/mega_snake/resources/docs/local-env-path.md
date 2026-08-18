Resolves the local environment file created by `init-local-config` — the `KEY=value` file whose
variables the generated configuration file exports on every shell startup.

## Notes

Its stdout is consumed by command substitution inside `config_setup.sh`:

```bash
local_env_file=$(mgsnake local-env-path)
```

so the command prints the path and nothing else. Diagnostics go to stderr precisely so this stays
parseable at any log level.
