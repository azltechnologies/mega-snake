Skill discovery files let AI agent runtimes (GitHub Copilot, Claude) present the `mgsnake` command
reference to an assistant without embedding it in the system prompt. The agent reads `SKILL.md` from
the configured skill directory and gains the same reference a human would find in `COMMANDS.md`.

**The reference is split in two, and the split is the point.** Both runtimes load a skill's body
eagerly the moment the skill triggers, so everything inside `SKILL.md` is spent from the assistant's
context before it knows which command it needs. `SKILL.md` therefore carries only the frontmatter
and a command index — name, aliases and one-line description, around 90 lines — while the full
reference lives beside it in `reference.md`, which the assistant opens only when it needs the
options, defaults and caveats of a specific command. Cheaper still, and what the index recommends
first: `mgsnake man <command>`, which renders one command's entry and always reflects the installed
version rather than whatever was generated last.

`reference.md` is identical to what `generate-docs` would write to `COMMANDS.md`, and the index is
rendered from the same introspection pass, so neither file can drift from the CLI or from the other.
Regenerate with `generate-skill` whenever you regenerate `COMMANDS.md`.

## Output

Two files are written into the chosen skill directory (or both):

- `.github/skills/mgsnake/` — GitHub Copilot skill directory
- `.claude/skills/mgsnake/` — Claude skill directory

| File | Contents |
| ---- | -------- |
| `SKILL.md` | The YAML frontmatter both runtimes read to register the document as a skill — its `name` and the `description` that tells the assistant when the skill applies — then how to read a full command entry, then the command index. |
| `reference.md` | The complete command reference: every synopsis, option table, epilog and prose fragment. Not loaded until the assistant opens it. |

A `SKILL.md` without the frontmatter header is never loaded, so the frontmatter is part of the
generated content and `--check` compares it like any other line. `--check` validates **both** files,
so a stale `reference.md` is reported even when `SKILL.md` is current.

The command asks two questions before writing anything: which assistant to target, and how the
resulting files should be tracked in git.

- **exclude (e)** — appends the directory to `.git/info/exclude`, keeping it machine-local and
  uncommitted. Best for teams that do not all use the same AI assistant.
- **gitignore (g)** — adds the directory to `.gitignore`. Use this when the whole team uses the
  same assistant and has agreed to exclude skill files from the repository.
- **versioned (v)** — leaves the files as-is so they can be committed. Use this when you want to
  ship the skill alongside the project so contributors get it automatically after cloning.

## Examples

```bash
# Write the files: pick the target assistant and the git-tracking preference at the prompts
mgsnake generate-skill

# Verify that the skill files present on disk are up to date, without writing anything
mgsnake generate-skill --check
```

## Notes

**Writing always asks.** Both questions are asked on every run, including a re-run that would
rewrite an identical file. There is no non-interactive write mode, so this command cannot be put in
a git hook or a CI step without something to answer the prompts; use `--check` there instead, which
never prompts. Both answers are collected before the first file is written, so abandoning either
prompt leaves the working tree untouched.

`--check` only validates skill files that already exist on disk, and it checks each file
independently. If none are present it exits successfully — the command does not mandate that skill
files exist, only that the ones you keep are not stale. On a checkout where the skill files are
excluded from git, that means the check has nothing to look at and always passes.

The command requires no workspace and no git repository, so it runs anywhere `mgsnake` is installed.
The git-tracking step is the exception: outside a repository it is skipped with a warning rather
than failing.
