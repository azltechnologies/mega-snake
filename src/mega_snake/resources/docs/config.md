The repository already had three configuration layers and not one of them could be written to:
`config.properties` ships inside the wheel and is replaced on every install, `AppProperties` is a
per-process singleton kept deliberately immutable, and the local config/env files are a shell
prelude the CLI writes once and never reads back. This command is the missing middle piece — state
the CLI both writes and reads — and it is what lets the Jira commands stop asking for a project key
on every single call.

Subcommands:

| Subcommand | What it does |
|---|---|
| `get KEY` | Prints the resolved value. Only the value reaches stdout, so `$(mgsnake config get jira.project_key)` is safe. Exits 1 when nothing defines it. |
| `set KEY VALUE [--global]` | Stores the setting, atomically. |
| `unset KEY [--global]` | Removes it from that one scope only. |
| `list [--scope repo\|global\|all]` | Prints `key=value` lines of what is on disk. |
| `export [--shell] [--scope]` | Prints export statements for the `global` scope, meant to be evaluated from the shell profile. |

## Output

Two files, one per scope, both plain sorted JSON:

- `<git-dir>/mgsnake/state.json` — the `repo` scope, the default target of `set` and `unset`. Living
  inside `.git` means it is never committed without touching `.gitignore` or `.git/info/exclude`, it
  is per-clone, and it dies with the clone. `workspace_temp` was rejected for this: it is explicitly
  disposable, and state that evaporates is not state.
- `~/.config/mgsnake/state.json` (`%APPDATA%\mgsnake\state.json` on Windows) — the `global` scope.

Writes go through a temporary file in the same directory followed by a rename, so an interrupted run
cannot leave behind a half-written file that would then break every other command.

## Examples

```bash
mgsnake config set jira.domain azltech.atlassian.net --global
mgsnake config set jira.email dev@example.com --global
mgsnake config set jira.project_key TAROTAPP

mgsnake jira-board            # no arguments needed any more

# In the shell profile: the user-wide settings only, which is what `export` defaults to.
eval "$(mgsnake config export --shell bash)"
```

## Notes

Reads resolve through **environment variable → repo → global**. The environment sits on top on
purpose: every workflow that exported `JIRA_DOMAIN` and friends keeps working untouched, so
adopting the store can be gradual.

Credentials are refused, not warned about. Any name matching `token`, `secret`, `password`,
`passwd`, `credential` or `api_key` fails with an error and nothing is written. `JIRA_API_TOKEN` and
`GITHUB_TOKEN` stay in the environment: a plaintext credential in a state file is worse than an
exported variable precisely because it persists and is forgotten.

Names must be lowercase and dotted (`jira.field.story_points`), which is what keeps the file
navigable instead of turning into a flat junk drawer.

The whole group runs before any initialization, so it works outside a configured environment and
even before `MEGA_SNAKE_SHELL` exists. Outside a git repository the `repo` scope simply does not
exist: reads fall back to the global one, and writes say so and suggest `--global`.

Settings the Jira commands read: `jira.domain`, `jira.email`, `jira.project_key`, `jira.board_id`,
`jira.field.story_points` and `jira.field.sprint`. The last three are written by the commands
themselves as a cache; removing them just forces a fresh resolution.

`export` covers the `global` scope by default, and that default is load-bearing. An environment
variable outranks every scope, and a shell profile runs in whatever directory the terminal happened
to open in — so exporting the `repo` scope from there would pin one clone's `jira.project_key` and
`jira.board_id` onto the whole session, and every *other* clone would then resolve them from the
environment. `mgsnake jira-issues` in a second repository would download the first one's board, with
no warning and exit code 0. `--scope repo` and `--scope all` are still there for anyone who wants
exactly that, per shell rather than per profile.
