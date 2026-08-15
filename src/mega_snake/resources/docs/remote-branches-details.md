A branch counts as merged when it was merged, fast-forwarded, **rebased**, or **squashed** into the
main branch — the last two are detected by patch id, so branches that were squash-merged through a
PR are correctly reported as merged instead of lingering as unmerged noise.

Comparison is always against the remote main branch, never the possibly stale local copy.

## Output

Creates `workspace_temp/remote_branches.txt` with per-branch details: author, last commit date, and
ahead/behind counts.

## Notes

Requires a remote. Feed the output to `remote-branches-cleanup` to act on it.
