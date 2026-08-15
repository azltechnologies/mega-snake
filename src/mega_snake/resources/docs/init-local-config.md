Developers usually have machine-specific tokens, paths and aliases that must never be committed.
This command generates a shell-specific file (`.sh` or `.ps1`) that is **ignored by Git** and sourced
by the main environment, so the project can stay "convention over configuration" while still leaving
room for per-machine configuration.

Custom shell function definitions are supported, not just environment variables.

## Notes

Reload it in the current session with `mgsnake_reload`, defined by the shell init script (see
`shell-path`).
