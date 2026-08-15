Useful for code reviews, progress comments on a ticket, and release notes: it answers "what did I
touch since master?" without scrolling through `git log`.

## Output

Writes three files to `workspace_temp/diff_tree/` and opens them in VS Code:

- `diff_tree.txt` — the visual tree of created, modified and deleted files.
- `diff_changes.txt` — the Git-style patch for those files.
- `diff_commit.txt` — the commit list (hash, date, message), newest first.

The tree and the patch follow `--scope`. The commit list cannot, since uncommitted work has no
commits, so pending files are prepended instead as `Unstaged files:` and `Staged files:` sections
above the newest commit — each one only when the scope covers it.

## Notes

The output directory is wiped and recreated on every run. No remote is required: when the
repository has none, the comparison falls back to the current local branch.
