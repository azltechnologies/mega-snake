Useful for code reviews, progress comments on a ticket, and release notes: it answers "what did I
touch since master?" without scrolling through `git log`.

Both ends of the comparison move independently: `--origin-hash` sets where it starts, `--target-hash`
sets where it ends. With both, the range is fully explicit and not anchored to the current checkout,
which is what makes it possible to reconstruct a past release from the two commits that bound it.

## Output

Writes three files to `workspace_temp/diff_tree/` and opens each one in VS Code:

- `diff_tree.txt` — the visual tree of the affected paths. Every entry is tagged with a marker for
  what happened to it (added, modified, deleted, renamed, copied, type-changed, unmerged), and the
  file closes with a per-marker legend and its totals.
- `diff_changes.txt` — the Git-style patch for those files.
- `diff_commit.txt` — the commit list (hash, date, message), newest first.

Alongside them it reconstructs the affected paths as a real directory tree under
`workspace_temp/diff_tree/diff_tree_dummy_repo/`, which is what the tree above is rendered from.
Each file there holds its contents **as of the origin of the comparison** — the "before" version,
so you can open it next to your working copy. Files you added have no before-version and are left
empty, and binary files carry a placeholder instead of their bytes rather than dumping raw data
into a text snapshot.

The tree and the patch follow `--scope`. The commit list cannot, since uncommitted work has no
commits, so pending files are prepended instead as `Unstaged files:` and `Staged files:` sections
above the newest commit — each one only when the scope covers it.

## Examples

```bash
# Everything on this branch that master does not have
mgsnake dt

# A past release, reconstructed from the two commits that bound it
mgsnake dt -o 85652b7 -t 79108b6
```

## Notes

The output directory is wiped and recreated on every run, so nothing from a previous comparison
survives into the current one — including the reconstructed tree, which is rebuilt from scratch.

No remote is required: when the repository has none, the command asks for the local main branch to
compare against. With a remote, the main branch is resolved from it and the command offers to
fetch and prune it first, so the comparison is against a main branch as fresh as you want it.

The rejection of an incompatible `--target-hash`/`--scope` pair happens before the output directory
is touched, so a rejected invocation leaves the previous run's files intact instead of wiping them
and then aborting.
