A branch counts as merged when it was merged, fast-forwarded, **rebased**, or **squashed** into the
main branch — the last two are detected by patch id, so branches that were squash-merged through a
PR are correctly reported as merged instead of lingering as unmerged noise.

Comparison is always against the remote main branch, never the possibly stale local copy.

Local branches with no counterpart on the remote are reported too, judged by the same rules and
against that same remote main branch. They are the branches a remote-only listing structurally cannot
see, and the most common form of dead branch: once a pull request is merged the hosting platform
usually deletes the branch, `git fetch --prune` drops the remote-tracking reference, and the local
branch is left behind indefinitely.

## Output

Creates `workspace_temp/remote_branches.txt` with per-branch details: author, last commit date, and
ahead/behind counts.

The report does not mark which entries are local-only; the deletion step resolves that from the
references themselves, and says so per branch.

## Notes

Requires a remote. Feed the output to `remote-branches-cleanup` to act on it.
