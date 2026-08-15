The whole board goes to a file rather than through the MCP server on purpose: the skills need to
slice the same dataset many times over (by epic, by assignee, by status, by sprint), and paying for
a fresh remote round trip per question is both slow and rate-limited. One download, then `jq`.

## Output

A JSON array written atomically to `workspace_temp/jira_board_issues.json`, or to `--output`. Every
entry has this shape:

```jsonc
{
  "id": "10001",
  "link": "https://<domain>/rest/api/2/issue/10001",
  "key": "TAROTAPP-1",
  "fields": {
    "summary": …, "statuscategorychangedate": …, "created": …, "resolutiondate": …,
    "lastViewed": …, "updated": …, "description": …,
    "issuetype": { "name": …, "subtask": …, "entityId": …, "hierarchyLevel": … },
    "parent": { "id": …, "key": … },
    "project": { "id": …, "key": …, "name": … },
    "status": { "id": …, "name": …, "statusCategory": { "id": …, "key": …, "name": … } },
    "workratio": …, "issuerestriction": …,
    "priority": { "id": …, "name": … },
    "labels": [ … ],
    "storyPoints": …,
    "assignee": { "accountId": …, "displayName": …, "emailAddress": …, "timeZone": … },
    "creator":  { … same shape … },
    "reporter": { … same shape … },
    "votes": { "votes": …, "hasVoted": … },
    "attachment": [ { "id": …, "filename": …, "mimeType": …, "size": …, "contentUrl": …, "author": { … } } ],
    "attachmentsCount": …,
    "comment": [ { "id": …, "created": …, "updated": …, "jsdPublic": …, "body": …, "author": { … }, "updateAuthor": { … } } ],
    "commentCount": …,
    "sprint": [ { "id": …, "name": …, "state": …, "startDate": …, "endDate": …, "completeDate": … } ]
  },
  "activeSprint": true
}
```

A nested object that Jira returned as `null` becomes an object whose values are all `null`, never
`null` itself — `parent` above all, since `.fields.parent.key == null` is the documented way to find
orphaned stories and it throws the moment `parent` itself is null.

## Examples

```bash
mgsnake jira-issues                              # stored project key, default destination
mgsnake jira-issues TAROTAPP -o /tmp/board.json
mgsnake jira-issues --quiet                      # for scripts and CI

# What is in the current sprint, with points and assignee
jq -r '.[] | select(.activeSprint)
        | "\(.key)\t\(.fields.storyPoints // "-")\t\(.fields.assignee.displayName // "unassigned")\t\(.fields.summary)"' \
   workspace_temp/jira_board_issues.json

# Stories with no epic
jq -r '.[] | select(.fields.parent.key == null) | .key' workspace_temp/jira_board_issues.json

# Points per assignee in the active sprint
jq '[.[] | select(.activeSprint)] | group_by(.fields.assignee.displayName)
     | map({assignee: .[0].fields.assignee.displayName, points: (map(.fields.storyPoints // 0) | add)})' \
   workspace_temp/jira_board_issues.json
```

## Notes

The story points and sprint custom fields are looked up by name (`Story Points`, or
`Story point estimate` on team-managed projects, and `Sprint`) and cached per clone. Their ids are
allocated per Jira instance, so the hardcoded `customfield_10016`/`customfield_10020` of the shell
version projected `null` on any other tenant without saying anything. If the names cannot be found
at all, those ids are used as a last resort and a warning says so.

If the values you get differ from the old script's, the new ones are the correct ones.

The download reads the board's own filter, so "every issue of the board" means exactly what Jira
means by it — including issues that live outside the project when the filter says so.

Progress goes to the console and the data only to the file, so `--quiet` is safe to combine with
anything. Every failure exits 1 with the reason on stderr.

On a corporate machine with a TLS-inspecting proxy the request layer will not see the corporate root
CA, because it validates against its own bundled certificate store rather than the system one. Point
`REQUESTS_CA_BUNDLE` at the corporate bundle:

```bash
export REQUESTS_CA_BUNDLE=/etc/ssl/certs/corporate-ca-bundle.crt
```

Never disable verification instead.
