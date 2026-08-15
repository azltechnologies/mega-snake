`release_type` selects how the release is published:

| Value | Meaning |
|---|---|
| `p` | Pre-release (`--prerelease`) |
| `l` | Latest (`--latest`) — asks for confirmation before replacing the current latest |
| `r` | Regular release (`--latest=false`) — keeps the current *latest* untouched, restoring it if GitHub moves the pointer anyway |

Publishing is delegated to the [`gh`](https://cli.github.com) CLI, which means it reuses the GitHub
authentication you already have — there is no token to configure here.

## Notes

Light-weight: it runs from anywhere, no workspace required. When `branch` is omitted the release is
cut from the current branch.
