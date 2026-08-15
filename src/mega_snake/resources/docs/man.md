`--help` answers "what are the flags?"; this answers "how does this command actually work?". It is
the reading form of the same reference published as `COMMANDS.md`, without leaving the terminal and
without a browser.

Nothing is installed into `/usr/share/man` and `mandb` is never invoked. `uv tool install` and
`pipx` place the package in an isolated environment and copy nothing to the system man path, so
`man mgsnake` would simply not resolve. Paging the document from inside the CLI is what makes this
work identically on Linux, macOS and PowerShell, where `man` does not exist at all.

## Examples

```bash
# The whole reference, grouped by module
mgsnake man

# One command
mgsnake man diff-tree

# Aliases work too — this is the same page as above
mgsnake man dt
```

## Notes

The document is rendered in memory from the live Click metadata and the packaged fragments, never
read from `COMMANDS.md`. That file lives in the repository and is not shipped inside the wheel, so
reading it would leave installed users with a command that only works in a source checkout.

Paging goes through the shell's pager (`less` on Unix, honouring `PAGER`). Styling is dropped
automatically when the pager cannot display it.
