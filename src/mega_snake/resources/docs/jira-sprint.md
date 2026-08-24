Answers "what is the team working on right now?" for the board behind a project, in the shape the
Jira skills consume.

## Output

Nothing on disk. The board lookup it performs first may populate the cached `jira.board_id`, exactly
as `jira-board` does.

Each entry carries `id`, `name`, `startDate`, `endDate`, `cloudDomain` and `boardId` — the same keys
the shell version produced, with `boardId` now a number.

## Examples

```bash
mgsnake jira-sprint | jq '.[0].name'
mgsnake jira-sprint TAROTAPP | jq -r '.[] | "\(.id) \(.name)"'
```

## Notes

**Breaking change.** The result is a JSON array. `getSprintInfo.sh` piped `.values[]` through `jq`
without wrapping it, so a single active sprint came out as a bare object and two came out as two
concatenated objects — which is not a JSON document at all and blows up in `json.load`. Filters that
assumed a single object need `jq '.[0]'`.

A board with no active sprint (a kanban board, or a sprint that was never started) prints `[]` and
exits 0. That is an answer, not a failure.

Boards are per project, so this always resolves the board first; with a warm cache that costs no
extra request.

The sprint listing is paged through to the end. Jira's Agile API pages with `startAt`/`isLast` and
never sends a continuation token, so a board with a long sprint history cannot hide an active sprint
on page two — which would otherwise show up in `jira-issues` as every one of that sprint's issues
being flagged `activeSprint: false`.
