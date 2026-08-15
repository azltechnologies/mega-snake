Interactive tool to clean up merged remote branches.

- Parses the output of `remote-branches-details`
- Interactively asks which merged branches to delete from the remote
- Prunes local references

Instead of passing complex objects between commands in memory, we use the filesystem (`workspace_temp/remote_branches.txt`) as an intermediate buffer. This pipeline via files allows the user to inspect (and potentially edit) the list of candidates before running the destructive cleanup command.
