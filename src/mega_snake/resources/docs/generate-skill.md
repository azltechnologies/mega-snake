Skill discovery files let AI agent runtimes (GitHub Copilot, Claude) present the full `mgsnake`
command reference to an assistant without embedding it in the system prompt. The agent reads
`SKILL.md` from the configured skill directory and gains the same reference a human would find in
`COMMANDS.md`, including every command synopsis, option table, and prose fragment.

The body is identical to what `generate-docs` would write to `COMMANDS.md`; both commands call the
same underlying renderer. Keeping them in sync is therefore automatic — regenerate with
`generate-skill` whenever you regenerate `COMMANDS.md`.

## Output

`SKILL.md` is written into the chosen skill directory (or both):

- `.github/skills/mgsnake/SKILL.md` — GitHub Copilot skill directory
- `.claude/skills/mgsnake/SKILL.md` — Claude skill directory

Each file opens with the YAML frontmatter both runtimes read to register the document as a skill —
its `name` and the `description` that tells the assistant when the skill applies — followed by the
command reference itself. A `SKILL.md` without that header is never loaded, so the frontmatter is
part of the generated content and `--check` compares it like any other line.

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

`--check` only validates skill files that already exist on disk. If none are present it exits
successfully — the command does not mandate that skill files exist, only that the ones you keep are
not stale. On a checkout where the skill files are excluded from git, that means the check has
nothing to look at and always passes.

The command requires no workspace and no git repository, so it runs anywhere `mgsnake` is installed.
The git-tracking step is the exception: outside a repository it is skipped with a warning rather
than failing.
