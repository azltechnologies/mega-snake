Useful for code reviews, progress comments on a ticket, and release notes: it answers "what did I
touch since master?" without scrolling through `git log`.

Both ends of the comparison move independently: `--origin-hash` sets where it starts, `--target-hash`
sets where it ends. With both, the range is fully explicit and no longer anchored to the current checkout,
which is what makes it possible to reconstruct a past release from the two commits that bound it.

## Output

Writes three files to `workspace_temp/diff_tree/` and opens them in VS Code:

- `diff_tree.txt` — the visual tree of created, modified and deleted files.
- `diff_changes.txt` — the Git-style patch for those files.
- `diff_commit.txt` — the commit list (hash, date, message), newest first.

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

The output directory is wiped and recreated on every run. No remote is required: when the
repository has none, the comparison falls back to the current local branch.

`--target-hash` only applies to the committed scope (`--scope c`, the default). The staged and unstaged
scopes read the index and the working tree, which exist only for HEAD, so combining them is rejected
rather than silently ignoring one of the two.
