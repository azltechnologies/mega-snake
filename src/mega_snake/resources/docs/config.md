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

`export` is a session bootstrap, not a synchronisation mechanism, and the difference matters
because what it writes becomes an environment variable — the layer that outranks *both* scopes. So
for any key a clone also defines in its `repo` scope, evaluating `export` from the shell profile
inverts the precedence above for the rest of the session:

```bash
mgsnake config set jira.domain companyA.atlassian.net --global
cd ~/clients/companyB && mgsnake config set jira.domain companyB.atlassian.net   # repo scope

eval "$(mgsnake config export --shell bash)"   # in ~/.bashrc: JIRA_DOMAIN=companyA...
cd ~/clients/companyB && mgsnake jira-issues   # ...so this talks to companyA. Exit 0.
```

Defaulting to `--scope global` is what keeps this narrow — the alternative, exporting `repo`, pins
one clone's board id and project key onto every other clone — but it does not close it, and it
cannot be closed from inside `export`: a shell profile runs in whatever directory the terminal
happened to open in, so filtering against "the current repository" would make the exported set
depend on where the terminal was launched, which is a worse failure because it is not reproducible.
The rule to work by is therefore: **export only the keys no clone overrides.** In practice that is
`jira.domain` and `jira.email`, which is exactly what the `global` scope is for.

Two conventions keep the file readable. A key ending in `.cached` is written by a command rather
than by you — `jira.field.sprint.cached` is what `jira-issues` worked out on its own — and the
bare key beside it is yours alone: nothing in the CLI writes `jira.field.sprint`, and when both
exist the bare one wins. That is why pinning a value actually sticks; see `jira-issues` for the
full story. Removing a `.cached` key is always safe, since the command that wrote it will work the
value out again.

Credentials are refused, not warned about, on the way in *and* on the way out. Any name matching
`token`, `secret`, `password`, `passwd`, `credential` or `api_key` fails `config set` with an error
and nothing is written; `JIRA_API_TOKEN` and `GITHUB_TOKEN` stay in the environment, because a
plaintext credential in a state file is worse than an exported variable precisely because it
persists and is forgotten. `config get` refuses to print one too — its first precedence layer is the
environment, so without that guard `mgsnake config get jira.api_token` would echo the live token to
stdout, and `mgsnake config get path` would echo `$PATH`. `config get` also insists on a real dotted
setting name for the same reason: it is a settings reader, not a general-purpose way to dump the
environment into a command substitution.

The file also carries a `mgsnake.state_version` marker, written the first time anything is stored
in that scope. It is what lets a one-time migration tell state written by an older version from
state you wrote yourself — a distinction the keys alone cannot make. It is metadata rather than a
setting, so `config list` and `config export` leave it out; it is plainly there if you read the file.

Names must be lowercase and dotted (`jira.field.story_points`), which is what keeps the file
navigable instead of turning into a flat junk drawer.

The whole group runs before any initialization, so it works outside a configured environment and
even before `MEGA_SNAKE_SHELL` exists. Outside a git repository the `repo` scope simply does not
exist: reads fall back to the global one, and writes say so and suggest `--global`.

An unusable state file (invalid JSON, or valid JSON that is not an object) is never silently
discarded, and it is never grounds for a hang either — the two failure modes this mechanism is built
to avoid. Four different behaviors apply, depending on the subcommand:

- **`set`, `unset` and `list` on one explicit scope** (`--scope repo` or `--scope global`) ask about
  that exact file, so from an interactive terminal they offer to back the broken file up next to
  itself (renamed, never deleted) and start a fresh empty one. Declining, or running
  non-interactively (a script, CI, a closed stdin), fails loudly instead, naming the broken file for
  manual repair.
- **`get` and `export` never prompt, on any terminal.** Both are meant to be consumed by a shell —
  `$(mgsnake config get ...)`, and `export` specifically `eval`'d from a shell profile on every new
  terminal — so a prompt on a corrupt file would hang a script's stdout capture, or a terminal's
  startup, instead of failing it in milliseconds.
- **`get` and `list --scope all` / `export --scope all`** merge both scopes, so a single broken one
  degrades instead of blocking a setting that only lives in the healthy scope — a warning naming the
  broken file is still printed once per run, but nothing is offered to fix it from there.
- **`export` on one explicit scope** (`--scope repo` or `--scope global`) still fails loudly on a
  broken file, same as `set`/`unset`/`list` — it is only the *prompt* that `export` never gets,
  never the failure itself.

A state file that cannot be *read* at all (wrong permissions, an I/O error) follows the same two
rules — an explicit scope fails, a merged read degrades with a warning — but is **never** offered
the backup-and-reset, on any terminal. Unreadable is not the same as corrupt: the contents are very
likely intact behind the wrong permissions, so renaming the file aside and starting over would
throw away recoverable settings to fix something `chmod` solves. The message names the file and
says so.

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
