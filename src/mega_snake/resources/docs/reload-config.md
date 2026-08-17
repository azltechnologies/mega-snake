Applies edits to the local configuration file without opening a new terminal. Sourcing that file is
what makes its functions, aliases and exported variables available, and a shell only does it at
startup — so after editing it, the running session keeps the old definitions until something
re-sources it. This is that something.

## Notes

A process cannot change the environment of the process that started it, which is a guarantee of the
operating system rather than a limitation of this tool. The command therefore does no work itself:
it reports the request through its exit status, and the `mgsnake` shell function installed by the
init script performs the sourcing inside the session that asked for it.

That function is the reason this works, so the command is only useful once
`config_setup.sh` / `config_setup.ps1` is sourced from the shell profile — see `shell-path`. Run
without it, the command exits with its status and nothing happens.

Commands that rewrite the local files (`working-env`, `set-java`, `set-gradle`, `set-maven`,
`init-local-config`) already emit the same request when they finish, so running this afterwards is
usually unnecessary. Reach for it after editing the file by hand.

Reloading the configuration file also reloads the environment file, because the generated
configuration file loads it on the way through.
