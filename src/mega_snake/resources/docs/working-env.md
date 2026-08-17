The "zero-config start" command: a single run should leave the IDE ready to code, so it is the one
to reach for on a freshly cloned repository.

On top of what the synopsis lists, it also sets up log watchers and GitHub query definitions, and it
 runs the Java, Gradle and Maven configuration steps for you — `set-java`, `set-gradle` and
 `set-maven` are only needed afterwards when you want to switch versions.

## Notes

Requires a valid Git repository. Developer-specific overrides are loaded before the defaults are
written, so anything you set through `init-local-config` wins over the values this command
generates.

Because it writes the local environment files, a successful run exits with status `29`. The
`mgsnake` shell function installed by the init script (see `shell-path`) reads that status and
re-sources them, so the environment it just configured applies to the current session.
