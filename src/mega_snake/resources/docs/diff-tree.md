Creates a visual diff tree of the current branch against master.

## Output
Generates a tree structure in `workspace_temp/diff_tree/` and opens it in VSCode. The tree and the changes patch follow the scope; the commit list adds the uncommitted work (`Unstaged files:` and `Staged files:`) above the most recent commit, for the sections the scope covers.
