Writes `java.import.gradle.home` and the `GRADLE_HOME` entry of `terminal.integrated.env.<os>` in the
`.code-workspace` file, keeping the Gradle the IDE imports with and the one your integrated terminal
calls on the same version.

## Notes

As with `set-java`, the `.code-workspace` file is read with a comment-preserving loader, so your
annotations are not stripped.

Also as with `set-java`, a successful run exits with status `29`, which the `mgsnake` shell function
(see `shell-path`) reads to re-source the local environment files, so the new `GRADLE_HOME` applies
to the current session.
