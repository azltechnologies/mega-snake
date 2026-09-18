Write a progress comment on a Jira story: what actually moved today, derived from the commits, in
the story's own thread — so the next person to open it does not have to read the git log to find out
where the work stands.

## Why this skill exists

A progress comment is worth writing and tedious to write. The facts are in the commit range, the
judgement is yours, and the two have to be merged into something a reader who was not there can
follow. `mgsnake diff-tree` produces the facts as three files on disk; this skill turns them into a
comment and refuses to publish it without approval.

## Cost rules

Two of the three files `diff-tree` writes are cheap and one is not, and the difference is the whole
of this section.

1. **Read `diff_commit.txt` and `diff_tree.txt`. Both, every time.** The first is the commit list —
   hashes, dates, subjects. The second is a plain text tree of the files added, modified and deleted.
   Both are small, both are ordinary text, and together they answer *what happened* and *where*,
   which is most of a progress comment.
2. **Never read `diff_changes.txt` whole.** That one is the full patch, and it routinely runs past
   100 KB. Open it only when a commit's subject and the files it touched still leave you unsure what
   actually changed, and then grep it for the file in question rather than printing it.
3. **`jq`, never a raw dump**, when listing the sprint's stories. Project only key, summary and
   status.
4. `mgsnake man diff-tree` and `mgsnake man jira-issues` explain either command in full, on demand.

## Steps

### 1. Get the baseline commit

The comment reports a *range*, so it needs the commit to compare against. **The user provides it.
If it was not given, ask — never guess it, and never assume the previous day's HEAD.**

### 2. Pick the story

If `workspace_temp/current_story.md` exists, it names the story already being worked on; confirm it
rather than asking again. Otherwise list the open stories of the active sprint and let the user
choose:

```bash
mgsnake jira-issues --quiet
jq -r '.[] | select(.activeSprint and .fields.status.name != "Done")
        | "\(.key)\t\(.fields.status.name)\t\(.fields.summary)"' \
   workspace_temp/jira_board_issues.json
```

Do not use a Jira MCP server for this sweep: one download answers it, and every remote call is
slower and rate-limited.

### 3. Produce the diff

```bash
mgsnake diff-tree -o <BASELINE_COMMIT>
```

This writes three files into `workspace_temp/diff_tree/`:

| File | What it holds | Read it |
| ---- | ------------- | ------- |
| `diff_commit.txt` | Every commit in the range, newest first: hash, date, message. | Always |
| `diff_tree.txt` | A text tree of the files added, modified and deleted. Small, and the fastest way to see the shape of the work. | Always |
| `diff_changes.txt` | The full patch. Routinely over 100 KB. | Only for a specific question, and grep it |

The command wipes and recreates that directory on every run, so there is nothing to clean up
beforehand. It compares the baseline against the current HEAD by default.

### 4. Draft the comment

Merge the facts with the judgement. A useful comment says:

- **What moved**, in plain language — not a restated commit list. Group the commits by what they
  accomplished.
- **Where it stands** against the story's acceptance criteria: what is done, what is left.
- **Anything that changed direction**, and why — the part a reader cannot reconstruct from the diff.
- **The commit range covered**, both ends explicitly: the baseline (exclusive) and the HEAD hash it
  ran up to. Without both, the next comment cannot start where this one ended.
- **A link to the pull request**, if you know it. If you do not, ask the user for it once — and if
  they say there is none, or would rather not, leave it out. Never construct a URL from a pattern you
  guessed: a link that goes nowhere is worse in a story thread than no link at all.

### 5. Get approval before publishing

**Show the drafted comment and wait.** Never publish without an explicit yes. If the user asks for
changes, redraft and show it again.

Publishing is the one step `mgsnake` does not do: it reads Jira, it does not write to it. Use
whatever write path the project already has — a Jira MCP server, the web UI, or the REST API with
the same credentials the `jira-*` commands use.

**If you have no way to publish, say so and offer the fallback**: write the approved comment to a
Markdown file under `workspace_temp/` and tell the user where it is, so they can paste it into the
story themselves. Do not report the comment as published when it was only drafted, and do not leave
approved work with nowhere to go.

### 6. Update the story context, only if it is there

**If `workspace_temp/current_story.md` exists**, append the published comment to it so the file keeps
matching the story and the next session starts from an accurate one.

**If it does not exist, do nothing.** Do not create it here. That file belongs to the `jira-continue`
skill, which knows the structure it is supposed to have; writing one from this side would produce a
file that looks like the real thing and is shaped differently, which is worse than its absence.

## Requirements

`jira.domain`, `jira.email` and the `JIRA_API_TOKEN` environment variable must be configured; see
`mgsnake man config`. `jq` must be on the PATH, and step 3 must run inside the git repository whose
commits are being reported.
