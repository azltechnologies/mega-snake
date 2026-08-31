Agent items let AI agent runtimes (GitHub Copilot, Claude) drive `mgsnake` inside your own project.
Each item is a Markdown document the runtime discovers by reading the YAML frontmatter at its top.

**The CLI reference is split in two, and the split is the point.** Both runtimes load a skill's body
eagerly the moment the skill triggers, so everything inside `SKILL.md` is spent from the assistant's
context before it knows which command it needs. The `mgsnake` skill therefore carries only the
frontmatter and a command index — name, aliases and one-line description, around 90 lines — while
the full reference lives beside it in `reference.md`, opened only when the options, defaults and
caveats of a specific command are actually needed. Cheaper still, and what the index recommends
first: `mgsnake man <command>`, which renders one command's entry and always reflects the installed
version rather than whatever was generated last.

`reference.md` is identical to what `generate-docs` would write to `COMMANDS.md`, and the index is
rendered from the same introspection pass, so neither file can drift from the CLI or from the other.

**Items can require other items.** A task skill that tells an assistant to run mgsnake commands is
useless to one that does not know those commands exist, so it requires the `mgsnake` skill and
selecting it installs both; an agent may likewise bundle components that do nothing on their own.
Dependencies are resolved to any depth, and the extra install is never silent — the selection list
shows what comes bundled *before* you choose, and the run then prints which item it added and which
selection asked for it. Files appearing in your working tree that you did not choose must be
explainable.

**Some items are bundled, not offered.** A component that only makes sense as part of something else
is kept out of the selection list, so it cannot be installed on its own by accident. It is still
reachable by name through `--item`, which is what leaves it an update path that does not require
reinstalling whatever bundles it.

**Two kinds of item, with different shapes on disk.** A **skill** owns a directory and may hold
several files; an **agent** is a single file — and its extension is not the same for both assistants,
so the layout is resolved per runtime rather than assumed.

## Output

| Kind | GitHub Copilot | Claude |
| ---- | -------------- | ------ |
| skill | `.github/skills/<name>/` | `.claude/skills/<name>/` |
| agent | `.github/agents/<name>.agent.md` | `.claude/agents/<name>.md` |

Inside a skill directory:

| File | Written for | Contents |
| ---- | ----------- | -------- |
| `SKILL.md` | every skill | The YAML frontmatter both runtimes read to register the document — its `name` and the `description` that tells the assistant when the skill applies — then the skill's body. |
| `reference.md` | the `mgsnake` skill only | The complete command reference: every synopsis, option table, epilog and prose fragment. Not loaded until the assistant opens it. |

A `SKILL.md` without the frontmatter header is never loaded, so the frontmatter is part of the
generated content and `--check` compares it like any other line. `--check` validates **every** file
of every skill, so a stale `reference.md` is reported even when its `SKILL.md` is current.

## Examples

```bash
# Interactive: pick the skills, the assistant and the git-tracking preference at the prompts
mgsnake install-agent-items

# Non-interactive, for a hook or a CI step: nothing is asked
mgsnake install-agent-items --item mgsnake --target b --tracking e

# Bring an existing installation up to date after upgrading mgsnake
mgsnake install-agent-items --item mgsnake --target l --tracking v

# Verify that the skill files present on disk are up to date, without writing anything
mgsnake install-agent-items --check
```

## Notes

**Every offered item is always listed, installed ones included.** Each entry shows its kind and is
annotated with where it currently stands — `installed`, `STALE` or `not installed`, per assistant — so a skill whose content
improved in a newer mgsnake can be refreshed. Hiding what is already on disk would leave no way to
update it: the run would report everything as installed and hand you a stale file with a successful
exit. Re-running is idempotent; a skill already present is simply rewritten with the current content.

**The selection is all-or-nothing.** Items are chosen as one comma-separated answer (or `all`), and
a single unrecognised name rejects the whole answer without installing anything. Dropping the
unknown entry and proceeding with the rest would act on a selection you never made, and report
success for it.

**An item is `STALE` when any of its files is.** For the `mgsnake` skill that means a current
`SKILL.md` beside an outdated `reference.md` reads as stale, which is the case worth seeing: the
index would look perfectly current while the document it points at described commands that no longer
exist.

**The prompts can all be skipped.** `--item`, `--target` and `--tracking` answer them up front, and
a run that supplies all three asks nothing — which is what makes the command usable from a git hook,
a `Makefile` or a CI step. Whatever is not supplied is still asked, and every answer is collected
before the first file is written, so abandoning a prompt leaves the working tree untouched.

`--check` only validates skill files that already exist on disk, and checks each one independently.
If none are present it exits successfully — the command does not mandate that skill files exist, only
that the ones you keep are not stale. It never prompts and never writes, so it is the mode to use in
CI.

The git-tracking choice applies to every directory written in that run:

- **exclude (e)** — appends them to `.git/info/exclude`, keeping them machine-local and uncommitted.
  Best for teams that do not all use the same AI assistant.
- **gitignore (g)** — adds them to `.gitignore`. Use this when the whole team uses the same
  assistant and has agreed to keep skill files out of the repository.
- **versioned (v)** — leaves the files as-is so they can be committed. Use this when you want to
  ship the skills alongside the project so contributors get them automatically after cloning.

The command requires no workspace and no git repository, so it runs anywhere `mgsnake` is installed.
The git-tracking step is the exception: outside a repository it is skipped with a warning rather
than failing.
