Sets `M2_HOME` in both the workspace terminal settings and the local shell config, and points VS
Code's Maven executable path at the detected installation.

## Notes

Intended for `pom.xml`-based projects. Run `maven-project-setup` afterwards to add the matching VS
Code task definitions.

A successful run exits with status `29`, which the `mgsnake` shell function (see `shell-path`) reads
to re-source the local environment files, so the new `M2_HOME` applies to the current session.
`maven-project-setup` writes no environment file and therefore exits `0`.
