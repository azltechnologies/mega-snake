---
name: changelog-from-history
description: Reconstruct or extend CHANGELOG.md for mega-snake by mapping each published version to the commit range that produced it, inspecting that range with `mgsnake diff-tree`, and writing a curated entry per version. Use when a release is missing from the changelog, when back-filling history, or when preparing the `## [X.Y.Z]` section that `.github/workflows/release.yml` requires before it will publish.
---

# Building a changelog entry from git history

`.github/workflows/release.yml` refuses to publish a version without a matching `## [X.Y.Z]` section in
`CHANGELOG.md`. This is how that section gets written from evidence instead of memory.

**The output is curated prose, not a commit dump.** The exhaustive commit list already exists in the GitHub
Release body (`--generate-notes`). Merge subjects in this repository read
`Merge pull request #58 from azltechnologies/upgrade`, which tells a user nothing — never paste them in.
Write what changed *for someone who installs `mgsnake`*.

## Step 1 — Map versions to commit ranges

This repository has **no release tags**, so the boundaries come from the commits that changed the `version`
field in `pyproject.toml`:

```bash
git log master --format="%h|%ad|%s" --date=short -L '/^version = /,+1:pyproject.toml' | grep -E "^[0-9a-f]{7}\|"
```

Then read the value each one *landed on*, since the log shows the commit, not the resulting version:

```bash
for c in <hashes from above>; do
  printf "%s  %s  %s\n" "$c" "$(git show -s --format=%ad --date=short $c)" \
    "$(git show $c:pyproject.toml | grep -m1 '^version = ')"
done
```

Build a three-column table — **version, base commit, tip commit** — where the base is the *previous*
version's bump commit and the tip is this version's. The range is therefore `(base, tip]`: exclusive at the
start, inclusive at the end. Work after the newest bump commit is `Unreleased`.

Cross-check the dates against the PyPI release history
(`https://pypi.org/project/mega-snake/#history`). If a date does not line up, the mapping is wrong — stop
and re-derive it rather than writing an entry from a range you do not trust.

## Step 2 — Inspect each range with `mgsnake diff-tree`

```bash
mgsnake dt -o <base> -t <tip> -d
```

`-t | --target-hash` is what makes this possible: without it the comparison always ends at the current `HEAD`, so
only the newest range could be inspected. `-d` skips the file-content snapshot, which is dead weight here.

This writes three files to `workspace_temp/diff_tree/`, and **the directory is wiped on every run** — copy
each range's output somewhere else before running the next one:

| File | What to read it for |
|---|---|
| `diff_tree.txt` | The shape of the change: which modules were added, modified, deleted. Read this first — it tells you what kind of release it was. |
| `diff_commit.txt` | The commit subjects, for intent the file tree cannot show. |
| `diff_changes.txt` | The actual patch. Consult it only to confirm a specific claim; it runs to thousands of lines. |

Two practical notes:

- `diff-tree` opens all three files in VS Code. When sweeping several ranges in one go, shadow the launcher
  (`PATH` with a no-op `code` script) so you do not open a window per file.
- Back up any existing `workspace_temp/diff_tree/` before starting, and restore it when done. It is the
  user's working output.

## Step 3 — Write the entry

One `## [X.Y.Z] - YYYY-MM-DD` section per version, newest first, with Keep a Changelog subsections
(`Added`, `Changed`, `Fixed`, `Removed`) — only the ones that apply.

- **Lead with the user-visible effect**, then the mechanism. "`diff-tree` crashed with a `UnicodeDecodeError`
  when a binary file appeared in the diff" beats "added binary detection to `_create_files`".
- **A version bump with no functional change says so**, explicitly. Silence reads as an omission.
- **Name new commands with their aliases**, the way a user will type them.
- **Do not invent significance.** If a range is one dependency bump, the entry is one line.

## Step 4 — Verify against the gate that will run in CI

The publish workflow validates the section. Run the same check before committing:

```bash
for v in <every version in the file>; do
  RELEASE_VERSION=$v python <the validation from .github/workflows/release.yml>
done
```

It must pass for every documented version, and **fail for a version that is absent** — confirm both. A
section that exists but holds only sub-headings or the `- Nothing yet.` placeholder is rejected, by design.

## Applies to

`CHANGELOG.md` at the repository root. Related: `.github/workflows/release.yml` (the gate),
`src/mega_snake/resources/docs/diff-tree.md` (the command's own docs), and section 5 of
`.github/copilot-instructions.md` (the release contract).
