Every local branch is paired with its remote counterpart (through its configured upstream) into a
single logical branch, so the report describes each branch once with both sides: a branch never
checked out shows only its remote side, and a branch whose remote copy was deleted on merge shows
only its local one. Those local leftovers are the most common form of dead branch — once a pull
request is merged the hosting platform usually deletes the branch, `git fetch --prune` drops the
remote-tracking reference, and the local branch lingers indefinitely.

A side counts as merged when it was merged, fast-forwarded, **rebased**, or **squashed** into the
main branch — the last two are detected by patch id, so branches that were squash-merged through a
PR are correctly reported as merged instead of lingering as unmerged noise. Comparison is always
against the remote main branch when one exists, never the possibly stale local copy. A branch is
*fully merged* only when every side it exists on is merged.

Before enumerating anything, the command offers to fetch and prune the remote so the inventory is
as fresh as you want it to be.

## Output

Creates `workspace_temp/remote_branches.md` and opens it in VS Code. The file is rewritten from
scratch on every run, so it always describes one single inventory rather than accumulating past
ones.

It opens with the context the report was built from — remote, main branch with both its local and
remote hashes, the filter that was applied, and the generation timestamp — so a report kept around
can still be read later without guessing which repository state produced it. Then comes one table
row per branch, newest commit first, with:

- **Status** — `merged`, `remote merged`, `local merged` or `unmerged`. The middle two are the ones
  worth looking at: they mean the two sides disagree, so the branch is not yet safe to delete.
- **Track / Sync** — `local_only` or `remote_only` when the branch lives on one side only,
  otherwise git's own tracking markers (`[ahead 1, behind 2]` and `>`, `<`, `=`, `<>`), and
  `[gone]` for a branch whose upstream was pruned.
- **Local hash / Remote hash** — both tips, abbreviated, with `-` where that side does not exist.
  They are shown side by side precisely because they can diverge, which is what the status columns
  above are summarizing.
- **Last commit, Author, Subject** — of whichever side the branch has, to identify the work at a
  glance.
- **Main ancestor** — the commit the branch and the main branch last had in common.

When nothing matches, the report is still written and says so in prose instead of leaving an empty
table to interpret.

## Notes

A remote is not required: without one, the command asks for the local main branch and reports the
local branches against it. A `--format` option to customize the columns and output shape is
planned; for now the table is fixed. `remote-branches-cleanup` builds this same inventory in memory
for its interactive deletion — this report is for inspection.
