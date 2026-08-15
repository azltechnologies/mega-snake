Writes `java.configuration.runtimes` and the `JAVA_HOME` entry of `terminal.integrated.env.<os>` in
the `.code-workspace` file, so the IDE's language server and the integrated terminal always agree on
which JDK is in use. It also configures the Java formatter settings.

## Notes

The `.code-workspace` file is JSON with comments. It is read with a comment-preserving loader, so
the annotations you leave in it survive the update.
