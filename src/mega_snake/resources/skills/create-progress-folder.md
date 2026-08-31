The following progress folder has been created at:

```!
timestamp=$(date '+%Y-%m-%d_%H-%M-%S')
path_file=$(mgsnake local-config-path)

dir="${path_file%/*}"
target="progress_${timestamp}"

mkdir -p "$dir/$target"
echo "$dir/$target"
```

Use this folder so that you and your sub-agents, if any, can document the results of each task.

Every report-producing stage gets its own Markdown file inside this folder, and those files are created **only** by the `create-progress-file` skill, invoked with the folder path above as its argument. Never create a file in this folder yourself and never make up a filename for it: invoke the skill and use the path it returns, verbatim.

Read-only sub-agents cannot write their report themselves, so they hand it back to you in their response and you are the one who writes it into the file the skill returned for them.

You may create a reusable function to list the available files in chronological order, making them easier to manage and/or pass to other sub-agents.
