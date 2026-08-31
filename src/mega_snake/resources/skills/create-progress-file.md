The following progress file has been created at:

```!
timestamp=$(date '+%Y-%m-%d_%H-%M-%S')

dir="$outputpath"
target="${timestamp}.md"

touch "$dir/$target"
echo "$dir/$target"
```

Use this file so that you and your sub-agents, if any, can document the results of each task performed.

This path is the **only** valid path for this report. Use it exactly as printed above: do not rename it, do not move it, and do not create a different file next to it because its name looks unhelpful. If you need another report file, invoke this skill again instead of inventing one.

If the sub-agent that owns this report is read-only, it cannot write here: it hands its report back to you and you are the one who writes that report into this file.
