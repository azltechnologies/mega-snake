# Project Instructions

@.github/copilot-instructions.md

---

# Notes for Claude only

**Everything above this line is shared.** `.github/copilot-instructions.md` is the repository's
conventions, read by Copilot and by Claude alike, and it is where a rule about *this codebase*
belongs. This section is read by Claude and by nothing else, so it holds what is true about the
**environment Claude runs in** rather than about the code — operational facts that would be noise in
a document Copilot also has to follow.

Keep the split that way. A convention about the project goes above; a constraint of the runtime goes
here.

## This file is read from `master`, not from the branch

`anthropics/claude-code-action` replaces a fixed set of paths with the default branch's copy before
the run starts, and logs it verbatim:

```text
Restoring .claude, .mcp.json, .claude.json, .gitmodules, .ripgreprc, CLAUDE.md, CLAUDE.local.md, .husky from origin/master (PR head is untrusted)
```

Two consequences, both easy to be caught out by:

- **An edit to this file does not take effect until it is merged.** A pull request that changes
  `CLAUDE.md` is reviewed by an agent still following master's version. This is deliberate — the
  file steers the agent, so a branch must not be able to rewrite its own reviewer's instructions —
  but it means these notes cannot be tested from a pull request, exactly like the workflows.
- **`.github/copilot-instructions.md` is _not_ on that list**, so it is read from the branch under
  review. A change to the shared conventions above *does* apply to the run that reviews it.

## Running inside a GitHub Actions workflow

Every workflow here passes `--allowed-tools` with a narrow list. In headless CI there is nobody to
approve anything, so a command that does not match a rule is simply refused — and the refusal looks
like the tool "not being available", which has already been mis-reported as *"I could not execute
the suite in this environment"* when the suite was perfectly runnable.

**The rules match the literal command prefix.** `Bash(uv:*)` permits a command that _starts with_
`uv`. It does not permit the same program reached by another name:

| What was tried | Result |
| --- | --- |
| `uv run pytest -q` | allowed |
| `.venv/bin/python -m pytest …` | **refused** — matches no prefix, and this is the one that cost a review its test run |
| `gh pr diff 55 > out.diff` | **refused** — output redirection is blocked, even inside the workspace |
| `gh pr diff 55 > f 2>&1; wc -l f` | **refused** — compound commands are split, and every part must be allowed |
| `(which uv; ls) \| head` | **refused** — "Contains subshell" |
| `gh pr comment N --body "…\n# Heading"` | **refused** — a newline followed by `#` inside a double-quoted argument trips an argument-safety check |

So: **one command, no pipe, no redirection, no `&&`, no `;`, no subshell, no `cd` and no leading
`env`/`timeout` wrapper.** When output is long, ask for less of it (`-q`, `--quiet`) rather than
piping into `tail`. Quote a `gh` comment body with **single** quotes — the double-quoted form fails
only when the body happens to start a line with `#`, which is exactly what a markdown summary does,
so it fails on the real comment and never on the test one.

**Reading and searching need no permission at all.** `Read`, `Grep` and `Glob` are not `Bash` and
are always available, whatever the allowlist says. Prefer them over `cat`, `grep` and `sed` in a
workflow: they always work, and they do not consume an allowlist rule. A narrow Bash allowlist
constrains what a run can *execute*, never what it can *read*.

**If a command is genuinely refused, say so and name it.** Silence, or a vague "could not run the
tests", is indistinguishable from not having tried — and the fix is usually one line in the
workflow's `--allowed-tools`, which nobody can write without knowing which command failed.

### The checks, in the form that works

```bash
uv run pytest -q
uv run ruff check src/mega_snake
uv run mypy src/mega_snake
uv run mgsnake generate-docs --check
```

`pytest`, `ruff` and `mypy` are installed in `.venv` and are not on `PATH`; `uv run` is the only
form that both matches the allowlist and resolves the binary.

### Session persistence

`claude-issue.yml`, `claude-pr.yml` and `claude-code-review.yml` persist the conversation across
runs, and each hands its state to the run through `--append-system-prompt` rather than expecting it
to be read from a file — the tool allowlist grants nothing that opens one. Report those values
(`restored-from`, `continue-flag`, the artifact name) as the temporary note in
`.github/copilot-instructions.md` requires; they are in the conversation already, so there is
nothing to look up.

The state travels as a **workflow artifact**, not an `actions/cache` entry. Since 2026-06-26 GitHub
issues a read-only cache token to untrusted triggers, and `issue_comment` — the trigger of this
whole conversation — is one of them, so every cache write from an issue thread was denied while the
job still went green. If you are ever tempted to move this back to the cache, that is the reason it
is not there. The full evidence is in the temporary note.

The review conversation is namespaced separately (`thread-kind: review`) from the `@claude` working
conversation on the same pull request. That is on purpose: a reviewer resuming the session that
wrote the code would be reviewing something it remembers writing.

#### You are told which turn you are. Never work it out yourself.

The system prompt of every run carries a **turn number**, computed by the workflow from a counter
stored beside the transcripts, plus a plain sentence saying what was restored. Those values describe
**this** run and take precedence over everything else in your context.

This is not a stylistic preference; it is a rule written from a failure. Three consecutive runs on
issue #73 chained perfectly — same session id, `--continue` passed, artifacts growing — and all three
reported the chain as broken. The second run resumed the first one's transcript, found a turn in it
that truthfully said *"first run, cache miss"*, and published that as its own state, while quoting its
real `restored-from` value one line below. The third inherited that story, expected a hit, read
"miss", and wrote a diagnosis of a bug that did not exist.

So:

- **A resumed conversation always contains the previous turn's report of its own session state**, and
  the thread's comments contain it as well — `claude-code-action` injects the issue body and comments
  into every run regardless of whether any session was restored. Both are stale by construction.
- **When your memory and the given values disagree, the values are right** and your memory is an
  earlier turn talking.
- **Never count runs from the conversation or from the comment history** to decide which turn you are.
  That inference is exactly what was got wrong; the number is handed to you so it does not have to be
  made.
