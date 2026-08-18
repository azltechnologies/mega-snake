Developers usually have machine-specific tokens, paths and aliases that must never be committed.
This command generates a shell-specific file (`.sh` or `.ps1`) that is **ignored by Git** and sourced
by the main environment, so the project can stay "convention over configuration" while still leaving
room for per-machine configuration.

Custom shell function definitions are supported, not just environment variables.

## Notes

Reload it in the current session with `mgsnake reload-config`.

This happens automatically: the command exits with status `29` when it succeeds, and the `mgsnake`
shell function installed by the init script reads that status and reloads the file for you.
A child process cannot change its parent's environment, so the reload has to happen in your shell.
If you invoke the executable directly — bypassing the function, or from a script — you will see the
`29` and no reload will run.
