Useful when you want a single, drift-resistant command reference: the generator pulls the public
CLI shape from Click itself and only uses these fragments for the extra narrative that `--help`
should not duplicate.

## Output

Writes a Markdown command reference to the target file (default: `COMMANDS.md`).

## Notes

This command is intentionally `no_init`: it does not require `MEGA_SNAKE_SHELL`, a workspace, or a
git repository, and it resolves the packaged fragments through `importlib.resources`.
