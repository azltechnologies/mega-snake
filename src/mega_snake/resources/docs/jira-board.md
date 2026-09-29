Resolving a board takes two round trips — project key to project id, then project id to board — and
the answer almost never changes. That is why the result is cached per clone: the first run pays for
the lookup and every later one answers from disk, with no HTTP call and, therefore, no credentials
needed at all.

## Output

One JSON object on stdout, and nothing else:

```jsonc
{
  "boardId": 1,                           // number, the Agile board behind the project
  "cloudDomain": "example.atlassian.net"  // string, the Jira Cloud domain it was resolved from
}
```

Nothing on disk except the cache entry: `jira.board_id` is written to the repository scope of the
state store (see `config`), but only when the resolved project matches the stored
`jira.project_key`. Passing a different project key explicitly neither reads nor writes that cache,
so one clone's board can never be served for somebody else's project.

## Examples

```bash
mgsnake jira-board                       # uses the stored project key
mgsnake jira-board TAROTAPP | jq .boardId
mgsnake jira-board --refresh             # after the project's boards changed
```

## Notes

**Breaking change.** `boardId` is now a number. The shell version emitted it through `jq --arg`, so
it was the string `"1"`, while `getSprintInfo` turned around and used it as a number — the two
disagreed with each other. Any `jq` filter comparing it against a string needs adjusting.

An unknown project is an error naming the key. The shell version let `jq -r '.id'` return the string
`null`, asked Jira for `?projectKeyOrId=null`, and printed `{"boardId": "null"}` without a word.

When a project has several boards you are asked which one, and the answer is cached. The prompt goes
to stderr so it cannot corrupt a captured stdout — although in a `$(...)` capture you will not see
it, so run the command once on its own (or with `--refresh`) to make the choice.

Requires `jira.domain`, `jira.email` and `JIRA_API_TOKEN`; see the `config` reference. On a corporate
machine with a TLS-inspecting proxy, point `REQUESTS_CA_BUNDLE` at the corporate CA bundle.
