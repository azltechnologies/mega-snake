The comment-killer crew is a set of AI agents that resolve one code review comment at a time, and
this command is the part of them that cannot be a prompt: the order of the stages, the paths, the
handoffs and the verdict. An orchestrating agent runs `start`, does exactly what the printed JSON
says, runs `next`, and repeats. Everything a model could improvise its way around — inventing a
file name, carrying on with an empty handoff, deciding by itself that the comment is already
resolved — is decided here instead, in code.

The crew works test-first, which is what makes its result checkable rather than merely plausible.
The **spotter** maps the code the comment touches, the **trapper** writes tests that fail today and
can only pass once the comment is honoured, and the **hitman** takes a baseline of the project's own
checks, makes those tests pass and compares against it. Install them with `install-agent-items`; the
spotter needs nothing installed, because it is the runtime's own exploring agent working from a
brief this command writes.

Nothing here talks to a model: it moves a mission from one stage to the next and answers the agents'
lifecycle hooks, so the rules that keep the crew honest ship and version with the CLI instead of as
scripts inside your repository.

## Output

Each mission gets a folder under the working path, named after the moment it opened:

- `workspace_temp/comment_killer/<timestamp>/01_brief.md` — the code review comment, verbatim.
- `…/02_map.md` — the spotter's map: every file and object it inspected, with line ranges, and
  whether each one is involved in the bug or was checked and ruled out.
- `…/03_trap.md` — the trap: the failing tests, the proof that they fail, the sketch of what has to
  change, the project rules that govern it and the verification commands its CI runs.
- `…/04_hit.md` — the hit report: what was changed, the baseline against the final run of every
  check, and anything the crew had to report rather than fix.
- `…/00_spotter_brief.md` and `…/.state.json` — the crew's own machinery: the brief handed to the
  spotter, and which stage the mission is on.

## Examples

```bash
# The orchestrating agent drives this; run it by hand only to inspect or resume a mission.
mgsnake comment-killer start "to_dict() mutates the enum member instead of composing a value"
mgsnake comment-killer next --mission 2026-09-16_01-00-34
mgsnake comment-killer status

# Teach the crew where this project files its tests, when it is not a convention the crew knows.
mgsnake config set ck.test_pattern 'verification/|_should\.py$'
```

## Notes

- **Every answer is an action on stdout, refusals included.** When the state machine refuses a call —
  a mission id that is malformed or names nothing, an unreadable state file, an ambiguous verdict —
  `next` and `status` print an `error` action carrying the whole message and exit with 113, so the
  orchestrator reads the refusal the same way it reads every other step, and a script still sees
  the failure in the status.
- **A mission is self-contained, so several can run at once.** Every action carries the id of the
  mission it belongs to — its folder's name — and the orchestrator passes it back with `--mission`,
  which is what lets two crews work two comments in parallel without sharing anything. It is an id
  rather than a path so that a working path with spaces in it never reaches a shell. Omitting it
  picks the newest mission, which is a convenience for a human typing by hand.
- **`comment-killer-guard` is for hooks, not for people**, which is why it is hidden from `--help`. It
  is a command of its own rather than part of this group because it has to answer in an environment
  where nothing of mgsnake's has been set up. It reads a hook payload on stdin and exits with status 2 to
  refuse a tool call: it holds the orchestrator to these three commands, keeps the trapper inside
  the project's test files, and stops any of them from rewriting the index, the stash, the branch or
  the history. The agents declare it themselves; you never call it.
- **The crew needs `MEGA_SNAKE_SHELL` in the assistant's own environment**, which a session started
  outside a profile-sourced terminal does not have. Until it does, the guard refuses every call and
  tells you what to add to the `"env"` block of `.claude/settings.local.json`; add it, restart the
  session, and the mission runs. mgsnake never edits that file for you.
- **`ck.test_pattern` widens the trapper's guard**, it never replaces it: your regular expression is
  added to the conventions the crew already recognises, so a partial pattern cannot cost you the
  ones your project does follow. An unusable expression is reported and ignored rather than being
  allowed to stop a mission.
- **The crew is Claude-only for now**, because its agents use per-agent tools, lifecycle hooks and an
  initial prompt. `install-agent-items` says so when it refuses to write them for GitHub Copilot.
- **The crew asks for permission like any other tool, and two rules spare it the interruptions.**
  An agent definition cannot grant permissions to itself, so the assistant will ask the first time
  the orchestrator runs this command and the first time a henchman runs your test suite. Granting
  `Bash(mgsnake comment-killer:*)` plus whatever your project's checks need — its test runner, its
  linter, its type checker — with `/permissions` or in `.claude/settings.local.json` is what lets a
  mission run start to finish without stopping. Nothing is lost by not granting them: the crew just
  waits for you.
- Only `start` offers to create the working path, the same way every other command that writes
  there does. `next` and `status` only read missions, so without the folder they report that there is
  none.
