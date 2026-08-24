Works from the same branch inventory as `remote-branches-details` — every local branch paired with
its remote counterpart, judged against the remote main branch — except that here it is never
written anywhere: it is built in memory and consumed on the spot, so the deletion always acts on
the repository as it is right now, not on a report that may have been generated hours ago.

A selected branch is deleted from the sides where it actually exists: the remote copy when the
branch has a remote side, the local copy when it has a local one. Neither side is assumed, because
a branch you never checked out has no local reference and a branch whose remote counterpart was
deleted on merge has no remote one — attempting the missing half would report a deletion failure
for something that was already gone.

Local deletion uses `git branch -D` rather than `git branch -d`: the branch has been confirmed merged
into the *remote* main branch, which is the question that matters, while `-d` refuses whenever the
local main copy is behind and has not seen the merge yet.

## Output

It writes no file. What it produces is a change to the repository, so the run itself is the output:
one prompt per candidate, then the deletions you approved.

Each prompt identifies the branch before you decide on it — name, last commit date, author, commit
hash and subject — and states its **Location**: `local`, `remote`, or `local and remote`. That last
line is the one to read, because it is exactly what will be deleted for that branch. Three answers
are accepted: **yes** marks it for deletion, **no** skips it, and **finalize** ends the review right
there, keeping everything selected so far and never asking about the remaining branches.

Nothing is deleted while you are answering. The deletions run once the review is over, each one
reported as it happens, and the remote-tracking references are pruned afterwards when anything was
removed from the remote. Answering `no` to everything is a legitimate outcome and leaves the
repository untouched.

## Notes

It takes no options: run it and follow the prompts. The command offers to fetch/prune first, so the
inventory is fresh. Deletion is `git push <remote> --delete <branch>` plus `git branch -D <branch>`,
and cannot be undone from here. A branch that fails to delete from the remote keeps its local copy
and does not stop the run. A remote is only required when a selected branch has a remote side, so a
local-only cleanup works in a repository without remotes.
