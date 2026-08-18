Writes `java.configuration.runtimes` and the `JAVA_HOME` entry of `terminal.integrated.env.<os>` in
the `.code-workspace` file, so the IDE's language server and the integrated terminal always agree on
which JDK is in use. It also configures the Java formatter settings.

## Notes

The `.code-workspace` file is JSON with comments. It is read with a comment-preserving loader, so
the annotations you leave in it survive the update.

Because it rewrites a local environment file, the command exits with status `29` on success. The
`mgsnake` shell function installed by the init script (see `shell-path`) reads that status and
re-sources the local environment files, so the new `JAVA_HOME` applies to the current session
without opening a new terminal.
