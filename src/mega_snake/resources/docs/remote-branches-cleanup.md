Consumes the report produced by `remote-branches-details` (and can re-run it first to refresh the
data), then deletes the branches you select and prunes the local references pointing at them.

Rather than passing objects between commands in memory, the two commands communicate through
`workspace_temp/remote_branches.txt`. That file is the point: you can inspect it — and edit it —
before running a destructive command against your remote.

A selected branch is deleted from both sides, but only where it actually exists: the remote copy is
removed when the remote-tracking reference is there, and the local copy when the local reference is.
Neither side is assumed, because a branch you never checked out has no local reference and a branch
whose remote counterpart was deleted on merge has no remote one — attempting the missing half would
report a deletion failure for something that was already gone.

Local deletion uses `git branch -D` rather than `git branch -d`: the branch has been confirmed merged
into the *remote* main branch, which is the question that matters, while `-d` refuses whenever the
local main copy is behind and has not seen the merge yet.

## Notes

It takes no options: run it and follow the prompts. Deletion is `git push <remote> --delete <branch>`
plus `git branch -D <branch>`, and cannot be undone from here. A branch that fails to delete from the
remote keeps its local copy and does not stop the run. Requires a remote.
