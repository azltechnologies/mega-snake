Resume work on a Jira story: rebuild the context that was lost between sessions, agree on the next
step, and leave a written record the next session can pick up from.

## Why this skill exists

The current state of a story is rarely in its description. It is in the **last comment** — what was
tried, what broke, what was decided. Reconstructing that by hand at the start of every session is
slow, and doing it by asking a Jira server question by question is slower and burns context on
payloads nobody reads.

`mgsnake jira-issues` downloads the whole board once into a JSON file. Every question after that is
a `jq` filter against a local file: no round trip, no rate limit, and nothing enters the
conversation except the fields actually needed.

## Cost rules

These are not style preferences. Breaking any of them multiplies the size of the session.

1. **Never print the downloaded JSON.** Do not `cat` it, do not read it into the conversation, do not
   pass it through unfiltered. Every read is a `jq` filter that projects only the fields being used.
   A board of a few hundred issues is megabytes; a single story's summary and comments is a few
   lines.
2. **Do not use a Jira MCP server or the REST API directly for this.** One download answers every
   question that follows. Repeated remote calls cost more and can be rate-limited mid-task.
3. **Read a command's reference only when needed.** `mgsnake man jira-issues` prints the full entry
   for one command — its flags, its output schema and its caveats — without loading the reference for
   everything else.

## Steps

### 1. Get the issue key

The user provides it. **If it was not given, ask for it — never guess.** As an alternative, offer the
stories of the active sprint so the user can pick one; that costs one small request:

```bash
mgsnake jira-sprint | jq -r '.[] | "\(.id)\t\(.name)"'
```

### 2. Take a fresh snapshot

Always download again. Do not reuse a `jira_board_issues.json` from an earlier session: the whole
point is the newest comment, and a stale file shows stale comments and a stale status with no
indication that it is out of date.

```bash
mgsnake jira-issues --quiet
```

That writes `workspace_temp/jira_board_issues.json`. Pass the project key as an argument when it is
not the stored default, and `-o <path>` to write somewhere else.

If `storyPoints` or `sprint` come back `null` on every issue, the cached custom field ids are stale:
re-run once with `--refresh`. Do not use `--refresh` routinely — it only re-resolves cached lookups,
and the download itself is always fresh.

### 3. Extract the one story

```bash
jq --arg key "PROJ-123" '
  .[] | select(.key == $key) | {
    key,
    summary: .fields.summary,
    status: .fields.status.name,
    points: .fields.storyPoints,
    epic: .fields.parent.key,
    activeSprint,
    description: .fields.description,
    comments: [.fields.comment[] | {author: .author.displayName, created, body}]
  }' workspace_temp/jira_board_issues.json
```

An empty result means the key is not on this board. Say so and ask — do not silently continue with
no story.

Note that a nested object Jira returned as `null` is projected as an object whose values are all
`null`, never as `null` itself. So `.fields.parent.key` is safe to read on a story with no epic, and
`select(.fields.parent.key == null)` is the way to find orphaned stories.

### 4. Present a structured summary

Never a raw dump of the JSON. Report, in prose and short tables:

- the summary, status, story points and epic;
- the acceptance criteria, read out of the description;
- **every comment**, with author and date — and call out the **most recent one** explicitly, since
  that is where the last state of the work lives.

### 5. Plan together

Discuss what remains against the acceptance criteria, and agree on the approach and the concrete
steps before writing any code.

### 6. Write the context file

Create or overwrite `workspace_temp/current_story.md` with the structure below, so the next session
starts from it instead of repeating this extraction. Sections marked optional may be omitted; every
other section is mandatory and must be filled — when there is nothing to say, say that explicitly
(for example "No acceptance criteria defined") rather than leaving it blank.

```md
# Story context <KEY>

> Story: **<title>**
> Description: <description>
> Epic: <epic key> (<epic title>)
> Points: <points> · Status: <status>
> Plan last updated: <date>

## Comments

| Author | Date | Comment |
| ------ | ---- | ------- |
| ...    | ...  | ...     |

## Acceptance criteria vs. actual state

| Criterion | State | Note |
| --------- | ----- | ---- |
| ...       | Met / Missing / Partial | ... |

## Current architecture (optional)

Relevant code and structure as it stands, before any change.

## Agreed approach

The decision taken on how to tackle the story, and why.

## Implementation steps

1. ...

## Open questions (optional)

Anything to resolve while implementing.

## Out of scope (optional)

Related work that belongs in a separate story.
```

## Requirements

`jira.domain`, `jira.email` and the `JIRA_API_TOKEN` environment variable must be configured; see
`mgsnake man config` and `mgsnake man jira-issues`. `jq` must be on the PATH.
