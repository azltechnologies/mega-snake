Skill discovery files let AI agent runtimes (GitHub Copilot, Claude) present the full `mgsnake`
command reference to an assistant without embedding it in the system prompt. The agent reads
`SKILL.md` from the configured skill directory and gains the same reference a human would find in
`COMMANDS.md`, including every command synopsis, option table, and prose fragment.

The file content is identical to what `generate-docs` would write to `COMMANDS.md`; both commands
call the same underlying renderer. Keeping them in sync is therefore automatic — regenerate with
`generate-skill` whenever you regenerate `COMMANDS.md`.

## Output

`SKILL.md` is written into the chosen skill directory (or both):

- `.github/skills/mgsnake/SKILL.md` — GitHub Copilot skill directory
- `.claude/skills/mgsnake/SKILL.md` — Claude skill directory

After writing the files the command asks how to track them in git:

- **exclude (e)** — appends the directory to `.git/info/exclude`, keeping it machine-local and
  uncommitted. Best for teams that do not all use the same AI assistant.
- **gitignore (g)** — adds the directory to `.gitignore`. Use this when the whole team uses the
  same assistant and has agreed to exclude skill files from the repository.
- **versioned (v)** — leaves the files as-is so they can be committed. Use this when you want to
  ship the skill alongside the project so contributors get it automatically after cloning.

## Examples

```bash
# First-time setup: pick the target assistant and the git-tracking preference interactively
mgsnake generate-skill

# Re-generate after updating command metadata (non-interactive if files already exist and match)
mgsnake generate-skill

# Verify that all existing skill files are up to date (CI-safe, exits non-zero if stale)
mgsnake generate-skill --check
```

## Notes

`--check` only validates skill files that already exist on disk. If no skill files are present it
exits successfully — the command does not mandate that skill files exist, only that existing ones
are not stale.

The command requires no workspace or git repository (`no_init` flag). It can run anywhere `mgsnake`
is installed, including CI environments, which makes `--check` suitable as a CI gate alongside the
equivalent `generate-docs --check`.
