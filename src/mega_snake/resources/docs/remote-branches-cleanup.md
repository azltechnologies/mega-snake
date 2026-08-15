Consumes the report produced by `remote-branches-details` (and can re-run it first to refresh the
data), then deletes the branches you select and prunes the local references pointing at them.

Rather than passing objects between commands in memory, the two commands communicate through
`workspace_temp/remote_branches.txt`. That file is the point: you can inspect it — and edit it —
before running a destructive command against your remote.

## Notes

Deletion is `git push origin --delete <branch>` and cannot be undone from here. Requires a remote.
