Exports the variables declared in an environment file into the shell session that runs the command,
so a project's settings can be picked up without restarting the terminal or writing an `export` for
each one.

The file format is deliberately plain, and is **not** a shell script:

```bash
# Comments start with a hash
DATABASE_URL=postgres://localhost:5432/dev
API_TOKEN="quoted values work too"
```

One `KEY=value` per line, no `export` keyword, blank lines and `#` comments ignored, and a matching
pair of surrounding single or double quotes stripped from the value. Because the file is parsed
rather than executed, it holds values only: command substitutions and variable references are not
expanded.

## Examples

```bash
# No argument: loads the local environment file (see `local-env-path`) if it exists,
# otherwise falls back to .env in the current directory
mgsnake load-env

# Load a specific file
mgsnake load-env config/staging.env
```

## Notes

A process cannot change the environment of the process that started it, which is a guarantee of the
operating system rather than a limitation of this tool. The command therefore does no work itself:
it reports the request through its exit status, and the `mgsnake` shell function installed by the
init script performs the exports inside the session that asked for it. That function finds the file
name by re-reading the arguments it was given, so global options are handled normally and
`mgsnake --log-level DEBUG load-env staging.env` loads `staging.env`.

That function is the reason this works, so the command is only useful once
`config_setup.sh` / `config_setup.ps1` is sourced from the shell profile — see `shell-path`. Run
without it, the command exits with its status and nothing happens.

Once the shell has performed the exports the request is fulfilled, so the function reports success
to whoever called it. The command is therefore safe inside `&&` chains and under `set -e`; only a
direct invocation that bypasses the function (`command mgsnake load-env`) shows the raw status.

A missing file is not an error: nothing is exported and the command stays silent, so an optional
`.env` can be loaded unconditionally from a startup script.

Called with no `env_file`, the shell first looks for the local environment file (the path
`local-env-path` prints, e.g. `.mgsnake.env` under `workspace_temp`) and loads that if it exists;
only when it does not does it fall back to `.env` in the current directory. That fallback applies
when you type `mgsnake load-env` yourself with no argument; a future release will let it be turned
on or off.

`config_setup.sh` / `config_setup.ps1` also load the local environment file automatically every time
a new session starts, but they do it by resolving `local-env-path` themselves and passing it in
explicitly, precisely so that automatic, unattended call never takes the `.env`-in-the-current-
directory fallback — only a local environment file that actually exists gets loaded at startup.

The environment file created by `init-local-config` is already loaded by the generated configuration
file, so it needs no explicit call here. Use this command for the other ones.
