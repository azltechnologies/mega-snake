# Available Commands

## Config Environment

### graphql-schema

Builds a consolidated GraphQL schema and introspection JSON from schema files in a directory.

**Synopsis:** `mgsnake graphql-schema [OPTIONS] SCHEMA_PATH`

**Aliases:** `graphql`, `gql`, `cgs`

| Option | Description |
| --- | --- |
| `-h, --help` | Show this message and exit. |

- `schema_path` — Directory containing the schema files; all files in it (subdirectories included) are merged into the consolidated schema

Frontend tooling (Apollo and most IDE plugins) cannot work from the raw SDL alone — it needs a full
introspection result to provide autocompletion and type checking. That is why this command emits two
files rather than one: the consolidated `.graphql` schema, and the `.json` introspection payload
those tools consume.

#### Output

Writes `schema.graphql` (consolidated SDL) and `schema.json` (introspection) to the
`workspace_temp` folder and opens both in VS Code.

#### Notes

Every file under the given directory — subdirectories included — is merged, so the directory is
the unit of composition, not an entry-point file. Keep only schema files in it.

### init-local-config

Creates or updates the local configuration file used for developer-specific shell settings.

**Synopsis:** `mgsnake init-local-config [OPTIONS]`

**Aliases:** `iload`, `ilc`

| Option | Description |
| --- | --- |
| `-o, --override` | Override the current local configuration file with a new one |
| `-h, --help` | Show this message and exit. |

Developers usually have machine-specific tokens, paths and aliases that must never be committed.
This command generates a shell-specific file (`.sh` or `.ps1`) that is **ignored by Git** and sourced
by the main environment, so the project can stay "convention over configuration" while still leaving
room for per-machine configuration.

Custom shell function definitions are supported, not just environment variables.

#### Notes

Reload it in the current session with `mgsnake reload-config`.

This happens automatically: the command exits with status `29` when it succeeds, and the `mgsnake`
shell function installed by the init script reads that status and reloads the file for you.
A child process cannot change its parent's environment, so the reload has to happen in your shell.
If you invoke the executable directly — bypassing the function, or from a script — you will see the
`29` and no reload will run.

### maven-project-setup

Creates or updates Maven tasks and log watchers in the current code-workspace when pom.xml is present.

**Synopsis:** `mgsnake maven-project-setup [OPTIONS]`

**Aliases:** `mps`

| Option | Description |
| --- | --- |
| `-o, --override` | Recreate existing Maven tasks and log watchers |
| `-h, --help` | Show this message and exit. |

Adds the task definitions under the `tasks` section of the current `.code-workspace` file —
`clean install`, `test`, `verify`, `dependency:tree` and `spring-boot:run` — together with the
matching log watchers, so each task's output lands in a watched log file.

#### Notes

Requires a `pom.xml` in the current directory. Existing tasks and watchers are left alone unless
`--override` is passed.

### set-gradle

Detects installed Gradle versions and sets the default Gradle version for the workspace and shell config.

**Synopsis:** `mgsnake set-gradle [OPTIONS]`

**Aliases:** `gradle`, `sg`

| Option | Description |
| --- | --- |
| `-o, --override` | Override the current Gradle version |
| `-h, --help` | Show this message and exit. |

Writes `java.import.gradle.home` and the `GRADLE_HOME` entry of `terminal.integrated.env.<os>` in the
`.code-workspace` file, keeping the Gradle the IDE imports with and the one your integrated terminal
calls on the same version.

#### Notes

As with `set-java`, the `.code-workspace` file is read with a comment-preserving loader, so your
annotations are not stripped.

Also as with `set-java`, a successful run exits with status `29`, which the `mgsnake` shell function
(see `shell-path`) reads to re-source the local environment files, so the new `GRADLE_HOME` applies
to the current session.

### set-java

Detects installed Java versions and sets the default Java version for the workspace and shell config.

**Synopsis:** `mgsnake set-java [OPTIONS]`

**Aliases:** `java`, `sj`

| Option | Description |
| --- | --- |
| `-o, --override` | Override the current Java version |
| `-h, --help` | Show this message and exit. |

Writes `java.configuration.runtimes` and the `JAVA_HOME` entry of `terminal.integrated.env.<os>` in
the `.code-workspace` file, so the IDE's language server and the integrated terminal always agree on
which JDK is in use. It also configures the Java formatter settings.

#### Notes

The `.code-workspace` file is JSON with comments. It is read with a comment-preserving loader, so
the annotations you leave in it survive the update.

Because it rewrites a local environment file, the command exits with status `29` on success. The
`mgsnake` shell function installed by the init script (see `shell-path`) reads that status and
re-sources the local environment files, so the new `JAVA_HOME` applies to the current session
without opening a new terminal.

### set-maven

Detects Maven installation (or uses --maven-home) and sets Maven paths for VS Code and local shell config.

**Synopsis:** `mgsnake set-maven [OPTIONS]`

**Aliases:** `maven`, `sm`

| Option | Description |
| --- | --- |
| `-m, --maven-home TEXT` | Explicit Maven home directory |
| `-h, --help` | Show this message and exit. |

Sets `M2_HOME` in both the workspace terminal settings and the local shell config, and points VS
Code's Maven executable path at the detected installation.

#### Notes

Intended for `pom.xml`-based projects. Run `maven-project-setup` afterwards to add the matching VS
Code task definitions.

A successful run exits with status `29`, which the `mgsnake` shell function (see `shell-path`) reads
to re-source the local environment files, so the new `M2_HOME` applies to the current session.
`maven-project-setup` writes no environment file and therefore exits `0`.

### working-env

Sets up the VS Code workspace with recommended extensions, default settings, tasks, launch configurations, and git exclusions. Also configures Java, Gradle, and Maven when applicable.

**Synopsis:** `mgsnake working-env [OPTIONS]`

**Aliases:** `cwe`, `env`

| Option | Description |
| --- | --- |
| `-h, --help` | Show this message and exit. |

The "zero-config start" command: a single run should leave the IDE ready to code, so it is the one
to reach for on a freshly cloned repository.

On top of what the synopsis lists, it also sets up log watchers and GitHub query definitions, and it
 runs the Java, Gradle and Maven configuration steps for you — `set-java`, `set-gradle` and
 `set-maven` are only needed afterwards when you want to switch versions.

#### Notes

Requires a valid Git repository. Developer-specific overrides are loaded before the defaults are
written, so anything you set through `init-local-config` wins over the values this command
generates.

Because it writes the local environment files, a successful run exits with status `29`. The
`mgsnake` shell function installed by the init script (see `shell-path`) reads that status and
re-sources them, so the environment it just configured applies to the current session.

## Dependency Audit

### scan-dependencies

Scans the project's locked dependencies for known vulnerabilities against the OSV advisory database, then files a GitHub issue for each new finding (package, installed version, recommended version, severity and advisory link), skipping findings that were already reported. The ecosystem (Python/uv, Java/Gradle/Maven, Node, or a generic OSV-Scanner audit) is auto-detected from the project's lockfiles, or can be forced with `--ecosystem`.

**Synopsis:** `mgsnake scan-dependencies [OPTIONS]`

**Aliases:** `sdep`, `audit`

| Option | Description |
| --- | --- |
| `--dry-run` | Scan and print findings without creating GitHub issues. |
| `--ecosystem [python\|java\|node\|osv]` | Force the ecosystem/auditor instead of auto-detecting it from the project's lockfiles. |
| `-h, --help` | Show this message and exit. |

The ecosystem is detected from the project's lockfiles, first match wins:

| Marker file | Ecosystem | Auditor |
|---|---|---|
| `uv.lock` | Python/uv | [`pip-audit`](https://github.com/pypa/pip-audit) |
| `build.gradle`, `build.gradle.kts`, `pom.xml` | Java (Gradle/Maven) | [OSV-Scanner](https://github.com/google/osv-scanner) |
| `package-lock.json` | Node | OSV-Scanner |
| *(nothing matches)* | generic fallback | OSV-Scanner |

OSV-Scanner covers the non-Python ecosystems because it reads the same OSV advisory database as
`pip-audit`, so findings stay comparable across stacks instead of depending on one tool per
ecosystem.

Any repo can reuse this by consuming `mgsnake`, regardless of its stack.

#### Notes

Issue de-duplication is by exact title and considers closed issues too, so a vulnerability you
already triaged and closed is not filed again on the next run.

## Diff Tree

### diff-tree

Creates a diff tree of changes and a commit list between two points in history. The comparison runs from master (or the commit given with --origin-hash) up to the current HEAD (or the commit given with --target-hash), which makes it possible to inspect a past range instead of only the current work.

**Synopsis:** `mgsnake diff-tree [OPTIONS]`

**Aliases:** `dt`, `tree`

| Option | Description |
| --- | --- |
| `-o, --origin-hash TEXT` | Commit hash to compare against instead of master |
| `-t, --target-hash TEXT` | Commit hash to compare up to, instead of the current HEAD. Requires --scope c (the default), since the index and the working tree only exist for HEAD; any other scope is rejected. |
| `-d, --delete-original-files` | Delete the generated copy of the original files in the diff tree |
| `-s, --scope [c\|s\|u]` | Changes to include: (c)ommitted only [default], committed and (s)taged, or also (u)nstaged and untracked. Only 'c' is compatible with --target-hash: the other two read the index and the working tree, which exist only for HEAD, so passing them together is rejected instead of silently ignoring one of them.  [default: c] |
| `-h, --help` | Show this message and exit. |

Useful for code reviews, progress comments on a ticket, and release notes: it answers "what did I
touch since master?" without scrolling through `git log`.

Both ends of the comparison move independently: `--origin-hash` sets where it starts, `--target-hash`
sets where it ends. With both, the range is fully explicit and no longer anchored to the current checkout,
which is what makes it possible to reconstruct a past release from the two commits that bound it.

#### Output

Writes three files to `workspace_temp/diff_tree/` and opens each one in VS Code:

- `diff_tree.txt` — the visual tree of the affected paths. Every entry is tagged with a marker for
  what happened to it (added, modified, deleted, renamed, copied, type-changed, unmerged), and the
  file closes with a per-marker legend and its totals.
- `diff_changes.txt` — the Git-style patch for those files.
- `diff_commit.txt` — the commit list (hash, date, message), newest first.

Alongside them it reconstructs the affected paths as a real directory tree under
`workspace_temp/diff_tree/diff_tree_dummy_repo/`, which is what the tree above is rendered from.
Each file there holds its contents **as of the origin of the comparison** — the "before" version,
so you can open it next to your working copy. Files you added have no before-version and are left
empty, and binary files carry a placeholder instead of their bytes rather than dumping raw data
into a text snapshot.

The tree and the patch follow `--scope`. The commit list cannot, since uncommitted work has no
commits, so pending files are prepended instead as `Unstaged files:` and `Staged files:` sections
above the newest commit — each one only when the scope covers it.

#### Examples

```bash
# Everything on this branch that master does not have
mgsnake dt

# A past release, reconstructed from the two commits that bound it
mgsnake dt -o 85652b7 -t 79108b6
```

#### Notes

The output directory is wiped and recreated on every run, so nothing from a previous comparison
survives into the current one — including the reconstructed tree, which is rebuilt from scratch.

No remote is required: when the repository has none, the command asks for the local main branch to
compare against. With a remote, the main branch is resolved from it and the command offers to
fetch and prune it first, so the comparison is against a main branch as fresh as you want it.

The rejection of an incompatible `--target-hash`/`--scope` pair happens before the output directory
is touched, so a rejected invocation leaves the previous run's files intact instead of wiping them
and then aborting.

## Documentation

### generate-docs

Generates the Markdown command reference by introspecting the registered CLI commands, rendering their help and options, and appending the command-specific fragment bodies.

**Synopsis:** `mgsnake generate-docs [OPTIONS]`

| Option | Description |
| --- | --- |
| `--output FILE` | Write the generated command reference to this file.  [default: COMMANDS.md] |
| `--check` | Render in memory, compare with the output file, and exit with an error when it is stale. |
| `-h, --help` | Show this message and exit. |

Useful when you want a single, drift-resistant command reference: the generator pulls the public
CLI shape from Click itself and only uses these fragments for the extra narrative that `--help`
should not duplicate.

#### Output

Writes a Markdown command reference to the target file (default: `COMMANDS.md`).

#### Notes

This command is intentionally `no_init`: it does not require `MEGA_SNAKE_SHELL`, a workspace, or a
git repository, and it resolves the packaged fragments through `importlib.resources`.

### generate-skill

Generates SKILL.md for AI agent skill discovery by introspecting the registered CLI commands and rendering the same reference as generate-docs. Creates the file under .github/skills/mgsnake/ for GitHub Copilot, .claude/skills/mgsnake/ for Claude, or both, then asks how those files should be tracked in git.

**Synopsis:** `mgsnake generate-skill [OPTIONS]`

| Option | Description |
| --- | --- |
| `--check` | Render in memory, compare with every skill file that already exists on disk, and exit with an error when any is stale. |
| `-h, --help` | Show this message and exit. |

Skill discovery files let AI agent runtimes (GitHub Copilot, Claude) present the full `mgsnake`
command reference to an assistant without embedding it in the system prompt. The agent reads
`SKILL.md` from the configured skill directory and gains the same reference a human would find in
`COMMANDS.md`, including every command synopsis, option table, and prose fragment.

The file content is identical to what `generate-docs` would write to `COMMANDS.md`; both commands
call the same underlying renderer. Keeping them in sync is therefore automatic — regenerate with
`generate-skill` whenever you regenerate `COMMANDS.md`.

#### Output

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

#### Examples

```bash
# Write the files: pick the target assistant and the git-tracking preference at the prompts
mgsnake generate-skill

# Verify that the skill files present on disk are up to date, without writing anything
mgsnake generate-skill --check
```

#### Notes

**Writing always asks.** Both questions — which assistant, how to track — are asked on every run, including a
re-run that would rewrite an identical file. There is no non-interactive write mode, so this command cannot be
put in a git hook or a CI step without something to answer the prompts; use `--check` there instead, which
never prompts.

`--check` only validates skill files that already exist on disk. If none are present it exits successfully —
the command does not mandate that skill files exist, only that the ones you keep are not stale. On a checkout
where the skill files are excluded from git, that means the check has nothing to look at and always passes.

The command requires no workspace and no git repository, so it runs anywhere `mgsnake` is installed. The
git-tracking step is the exception: outside a repository it is skipped with a warning rather than failing.

### man

Renders the command reference in the terminal and pages it, showing the whole document or a single command when one is named. The content is built from the live CLI metadata and the packaged fragments, so it never depends on a generated file being present.

**Synopsis:** `mgsnake man [OPTIONS] [COMMAND]`

| Option | Description |
| --- | --- |
| `-h, --help` | Show this message and exit. |

- `command` — command name or alias to display. Defaults to the full reference.

`--help` answers "what are the flags?"; this answers "how does this command actually work?". It is
the reading form of the same reference published as `COMMANDS.md`, without leaving the terminal and
without a browser.

Nothing is installed into `/usr/share/man` and `mandb` is never invoked. `uv tool install` and
`pipx` place the package in an isolated environment and copy nothing to the system man path, so
`man mgsnake` would simply not resolve. Carrying the reader inside the CLI is what makes the
reference available on every platform this tool supports, including PowerShell, where a system
`man` does not exist at all.

#### Examples

```bash
# The whole reference, grouped by module
mgsnake man

# One command
mgsnake man diff-tree

# Aliases work too — this is the same page as above
mgsnake man dt
```

#### Notes

The document is rendered in memory from the live Click metadata and the packaged fragments, never
read from `COMMANDS.md`. That file lives in the repository and is not shipped inside the wheel, so
reading it would leave installed users with a command that only works in a source checkout.

Paging goes through the shell's pager (`less` on Unix, honouring `PAGER`). Styling is dropped
automatically when the pager cannot display it.

On Windows the document is printed in full instead of being paged. Click 8.4.x cannot write text to
the temporary-file pager it selects for an interactive Windows console, so the command falls back to
plain output rather than failing. The content is identical; only the scrolling is the terminal's job
there.

## Git & Release Management

### remote-branches-cleanup

Builds the branch inventory (local, remote and paired branches) and iterates over the fully merged ones asking which to delete, removing each selected branch from the sides where it exists

**Synopsis:** `mgsnake remote-branches-cleanup [OPTIONS]`

**Aliases:** `rbc`

| Option | Description |
| --- | --- |
| `-h, --help` | Show this message and exit. |

Works from the same branch inventory as `remote-branches-details` — every local branch paired with
its remote counterpart, judged against the remote main branch — except that here it is never
written anywhere: it is built in memory and consumed on the spot, so the deletion always acts on
the repository as it is right now, not on a report that may have been generated hours ago.

A selected branch is deleted from the sides where it actually exists: the remote copy when the
branch has a remote side, the local copy when it has a local one. Neither side is assumed, because
a branch you never checked out has no local reference and a branch whose remote counterpart was
deleted on merge has no remote one — attempting the missing half would report a deletion failure
for something that was already gone.

Local deletion uses `git branch -D` rather than `git branch -d`: the branch has been confirmed merged
into the *remote* main branch, which is the question that matters, while `-d` refuses whenever the
local main copy is behind and has not seen the merge yet.

#### Output

It writes no file. What it produces is a change to the repository, so the run itself is the output:
one prompt per candidate, then the deletions you approved.

Each prompt identifies the branch before you decide on it — name, last commit date, author, commit
hash and subject — and states its **Location**: `local`, `remote`, or `local and remote`. That last
line is the one to read, because it is exactly what will be deleted for that branch. Three answers
are accepted: **yes** marks it for deletion, **no** skips it, and **finalize** ends the review right
there, keeping everything selected so far and never asking about the remaining branches.

Nothing is deleted while you are answering. The deletions run once the review is over, each one
reported as it happens, and the remote-tracking references are pruned afterwards when anything was
removed from the remote. Answering `no` to everything is a legitimate outcome and leaves the
repository untouched.

#### Notes

It takes no options: run it and follow the prompts. The command offers to fetch/prune first, so the
inventory is fresh. Deletion is `git push <remote> --delete <branch>` plus `git branch -D <branch>`,
and cannot be undone from here. A branch that fails to delete from the remote keeps its local copy
and does not stop the run. A remote is only required when a selected branch has a remote side, so a
local-only cleanup works in a repository without remotes.

### remote-branches-details

Creates a detailed markdown report of the repository's branches — local, remote and paired — filtered by merge status against the main branch

**Synopsis:** `mgsnake remote-branches-details [OPTIONS]`

**Aliases:** `rbd`

| Option | Description |
| --- | --- |
| `-f, --filter-by [m\|u\|a]` | filter branches by merge status against main branch:<br><br>'M' - fully merged branches (every existing side is merged)<br><br>'U' - not fully merged branches<br><br>'A' - all branches (default) |
| `-h, --help` | Show this message and exit. |

Every local branch is paired with its remote counterpart (through its configured upstream) into a
single logical branch, so the report describes each branch once with both sides: a branch never
checked out shows only its remote side, and a branch whose remote copy was deleted on merge shows
only its local one. Those local leftovers are the most common form of dead branch — once a pull
request is merged the hosting platform usually deletes the branch, `git fetch --prune` drops the
remote-tracking reference, and the local branch lingers indefinitely.

A side counts as merged when it was merged, fast-forwarded, **rebased**, or **squashed** into the
main branch — the last two are detected by patch id, so branches that were squash-merged through a
PR are correctly reported as merged instead of lingering as unmerged noise. Comparison is always
against the remote main branch when one exists, never the possibly stale local copy. A branch is
*fully merged* only when every side it exists on is merged.

Before enumerating anything, the command offers to fetch and prune the remote so the inventory is
as fresh as you want it to be.

#### Output

Creates `workspace_temp/remote_branches.md` and opens it in VS Code. The file is rewritten from
scratch on every run, so it always describes one single inventory rather than accumulating past
ones.

It opens with the context the report was built from — remote, main branch with both its local and
remote hashes, the filter that was applied, and the generation timestamp — so a report kept around
can still be read later without guessing which repository state produced it. Then comes one table
row per branch, newest commit first, with:

- **Status** — `merged`, `remote merged`, `local merged` or `unmerged`. The middle two are the ones
  worth looking at: they mean the two sides disagree, so the branch is not yet safe to delete.
- **Track / Sync** — `local_only` or `remote_only` when the branch lives on one side only,
  otherwise git's own tracking markers (`[ahead 1, behind 2]` and `>`, `<`, `=`, `<>`), and
  `[gone]` for a branch whose upstream was pruned.
- **Local hash / Remote hash** — both tips, abbreviated, with `-` where that side does not exist.
  They are shown side by side precisely because they can diverge, which is what the status columns
  above are summarizing.
- **Last commit, Author, Subject** — of whichever side the branch has, to identify the work at a
  glance.
- **Main ancestor** — the commit the branch and the main branch last had in common.

When nothing matches, the report is still written and says so in prose instead of leaving an empty
table to interpret.

#### Notes

A remote is not required: without one, the command asks for the local main branch and reports the
local branches against it. A `--format` option to customize the columns and output shape is
planned; for now the table is fixed. `remote-branches-cleanup` builds this same inventory in memory
for its interactive deletion — this report is for inspection.

## Light Weight

### create-release

Creates a GitHub release and tag: the new tag is the latest release's version with one of its components incremented, and the publication is delegated to the gh CLI.

**Synopsis:** `mgsnake create-release [OPTIONS] {p|r|l} [NOTES] [BRANCH]`

**Aliases:** `release`, `cr`

| Option | Description |
| --- | --- |
| `-p, --tag-pattern TEXT` | Pattern describing this project's release tags, where `$1`, `$2` and `$3` stand for the major, minor and patch numbers and everything else is literal (`$$` is a literal `$`). Defaults to `v$1.$2.$3`, or to the `release_tag_pattern` property when the project sets one. The pattern must match the latest release's tag, or the command stops. |
| `-s, --tag-suffix TEXT` | Pre-release label appended to the new tag (v1.2.4-<suffix>.N). Only valid for the 'p' and 'r' release types: a 'l' release takes over the latest pointer, which GitHub only ever grants to a plain version, so the two are mutually exclusive. |
| `-v, --version-part [patch\|minor\|major]` | Which component of the latest release's version to increment: 'patch' (the last number), 'minor' (the middle one, resetting the patch to zero) or 'major' (the first one, resetting the other two to zero).  [default: patch] |
| `-h, --help` | Show this message and exit. |

- `release_type` — 'p' (prerelease) | 'l' (latest) | 'r' (regular release)
- `notes` — release notes
- `branch` — branch to create the release from. Default is the current branch.

The release type decides how visible the release is once published. A **pre-release** is announced
as unfinished, so it never becomes the version GitHub offers by default — the usual choice for a
build meant for testing. A **latest** release is the opposite: it takes over the `latest` pointer
and becomes what users land on, which is why the command asks for confirmation first. A plain
**release** publishes without touching that pointer, so an older version stays the recommended one;
if GitHub moves it anyway, the command puts it back where it was.

The new tag is **derived, never typed**: the command reads the latest release, increments one
component of its version, and uses the result. That is what keeps the sequence continuous — the next
release always follows the one actually published, so two people cutting releases from different
checkouts cannot invent conflicting numbers.

`--version-part` chooses which component moves, and everything to its right restarts:

| From `v1.2.3` | Result | When to use it |
|---|---|---|
| `--version-part patch` *(default)* | `v1.2.4` | Fixes and changes that keep the same behaviour |
| `--version-part minor` | `v1.3.0` | New functionality that stays backwards compatible |
| `--version-part major` | `v2.0.0` | Breaking changes |

Resetting is what keeps the order monotonic: a minor bump that produced `v1.3.3` would sit above the
patches that follow it.

`--tag-suffix` marks the result as a pre-release build of that version — `v1.2.4-beta.0` — with a
counter that grows so the same version can be built repeatedly. The base version is derived the same
way as for a plain release, so a pre-release always announces a version that has **not** shipped yet:
`v1.2.5-beta.0` precedes `v1.2.5`, never trails `v1.2.4`. Pre-release tags do not raise the ceiling
either, so one beta cannot push the next release past it. It is **rejected for the `l` type**:
GitHub only grants the `latest` pointer to a plain version, so asking for a suffixed latest release
is something the platform cannot honour.

Publishing is delegated to the [`gh`](https://cli.github.com) CLI, which means it reuses the GitHub
authentication you already have — there is no token to configure here.

#### Examples

```bash
# A patch release from the current branch
mgsnake cr l

# A minor release with notes, cut from a specific branch
mgsnake cr l "Adds the man command" release/2.1 --version-part minor

# A prerelease build of the next patch: v1.2.4-beta.0, then -beta.1, ...
mgsnake cr p --tag-suffix beta

# A prerelease, which never takes over the latest pointer
mgsnake cr p
```

#### Notes

Light-weight: it runs from anywhere, no workspace required. When `branch` is omitted the release is
cut from the current branch.

The new tag is derived from the **highest `vX.Y.Z` tag in the repository**, not from the `latest`
pointer alone. Prereleases and `r` releases publish tags without moving that pointer, so it can sit
below tags that already exist; taking the maximum on every derivation is what makes the guarantee
hold unconditionally — a new tag can never land below one that was already published. The `latest`
release still decides whether the version is usable at all (see the note below).

#### Tag patterns

The tag format is **not** hard-coded. A pattern describes the tags this project already uses, with
`$1`, `$2` and `$3` standing for the major, minor and patch numbers; everything else is literal, and
`$$` is a literal `$`. The same string parses the current tag and renders the next one, so the two
can never disagree.

| Pattern | Latest tag | Next patch |
|---|---|---|
| `v$1.$2.$3` *(default)* | `v1.2.3` | `v1.2.4` |
| `$1.$2.$3` | `1.2.3` | `1.2.4` |
| `rel-$1_$2_$3` | `rel-1_2_3` | `rel-1_2_4` |

Set it per invocation with `--tag-pattern`, or per project with the `release_tag_pattern` property.
All three placeholders are required, since `--version-part` names exactly those three components.

The pattern must match the tag of the latest release, and the command stops when it does not — a
pattern that describes nothing in the repository would otherwise fail much later, with nothing
pointing at it as the cause. Only tags the pattern recognises count towards the next version, so tags
left over from a different scheme never raise the ceiling.

### expired-certs-jks

Analyze certificates in a Java KeyStore (JKS) file and report their validity status

**Synopsis:** `mgsnake expired-certs-jks [OPTIONS] JKS_PATH`

**Aliases:** `ecj`

| Option | Description |
| --- | --- |
| `-p, --password TEXT` | Custom password for the JKS file  [default: changeit; required] |
| `-v, --verbose` | Print the full certificate details of the expired certificates |
| `-h, --help` | Show this message and exit. |

- `jks_path` — Path to the Java KeyStore file to analyze.

Lists every alias in the keystore with its validity dates and raises a warning for the expired ones,
so you find out before a local dev environment breaks on an expired SSL certificate.

#### Examples

```bash
mgsnake expired-certs-jks /path/to/keystore.jks
mgsnake expired-certs-jks /path/to/keystore.jks --password mypassword
```

#### Notes

Parsing relies on `keytool -v -list` and expects its standard English date format
(`Mon Jan 01 00:00:00 UTC 2026`), which depends on the system locale and the installed Java
version. An alias without date information is warned about and skipped; a date in an unexpected
format aborts the run with an error rather than reporting a wrong status. For expired
certificates the command prints the `keytool` commands to delete and re-import them.

### load-env

Exports the variables declared in an environment file into the current shell session. The file is a plain list of KEY=value lines: no `export` keyword, one pair per line, `#` starts a comment, and surrounding single or double quotes around a value are stripped.

**Synopsis:** `mgsnake load-env [OPTIONS] [ENV_FILE]`

| Option | Description |
| --- | --- |
| `-h, --help` | Show this message and exit. |

- `env_file` — Path to the environment file to load. When omitted, the local environment file (see `local-env-path`, e.g. `.mgsnake.env` under workspace_temp) is loaded if it exists; otherwise `.env` in the current directory is loaded instead.

Exports the variables declared in an environment file into the shell session that runs the command,
so a project's settings can be picked up without restarting the terminal or writing an `export` for
each one.

The file format is deliberately plain, and is **not** a shell script:

```bash
# Comments start with a hash
DATABASE_URL=postgres://localhost:5432/dev
API_TOKEN="quoted values work too"
```

One `KEY=value` per line, no `export` keyword, blank lines and `#` comments ignored, and a matching
pair of surrounding single or double quotes stripped from the value. Because the file is parsed
rather than executed, it holds values only: command substitutions and variable references are not
expanded.

#### Examples

```bash
# No argument: loads the local environment file (see `local-env-path`) if it exists,
# otherwise falls back to .env in the current directory
mgsnake load-env

# Load a specific file
mgsnake load-env config/staging.env
```

#### Notes

A process cannot change the environment of the process that started it, which is a guarantee of the
operating system rather than a limitation of this tool. The command therefore does no work itself:
it reports the request through its exit status, and the `mgsnake` shell function installed by the
init script performs the exports inside the session that asked for it. That function finds the file
name by re-reading the arguments it was given, so global options are handled normally and
`mgsnake --log-level DEBUG load-env staging.env` loads `staging.env`.

That function is the reason this works, so the command is only useful once
`config_setup.sh` / `config_setup.ps1` is sourced from the shell profile — see `shell-path`. Run
without it, the command exits with its status and nothing happens.

Once the shell has performed the exports the request is fulfilled, so the function reports success
to whoever called it. The command is therefore safe inside `&&` chains and under `set -e`; only a
direct invocation that bypasses the function (`command mgsnake load-env`) shows the raw status.

A missing file is not an error: nothing is exported and the command stays silent, so an optional
`.env` can be loaded unconditionally from a startup script.

Called with no `env_file`, the shell first looks for the local environment file (the path
`local-env-path` prints, e.g. `.mgsnake.env` under `workspace_temp`) and loads that if it exists;
only when it does not does it fall back to `.env` in the current directory. That fallback applies
when you type `mgsnake load-env` yourself with no argument; a future release will let it be turned
on or off.

`config_setup.sh` / `config_setup.ps1` also load the local environment file automatically every time
a new session starts, but they do it by resolving `local-env-path` themselves and passing it in
explicitly, precisely so that automatic, unattended call never takes the `.env`-in-the-current-
directory fallback — only a local environment file that actually exists gets loaded at startup.

The environment file created by `init-local-config` is already loaded by the generated configuration
file, so it needs no explicit call here. Use this command for the other ones.

### local-config-path

Prints to stdout the path of the local configuration file (.sh or .ps1 depending on the active shell).

**Synopsis:** `mgsnake local-config-path [OPTIONS]`

**Aliases:** `lcp`

| Option | Description |
| --- | --- |
| `-h, --help` | Show this message and exit. |

Resolves the local configuration file created by `init-local-config`, picking the `.sh` or `.ps1`
variant according to the active shell.

#### Notes

Its stdout is consumed by command substitution inside `config_setup.sh`:

```bash
local_config_file=$(mgsnake local-config-path)
```

so the command prints the path and nothing else. Diagnostics go to stderr precisely so this stays
parseable at any log level.

### local-env-path

Prints to stdout the path of the local environment file.

**Synopsis:** `mgsnake local-env-path [OPTIONS]`

**Aliases:** `lep`

| Option | Description |
| --- | --- |
| `-h, --help` | Show this message and exit. |

Resolves the local environment file created by `init-local-config` — the `KEY=value` file whose
variables the generated configuration file exports on every shell startup.

#### Notes

Its stdout is consumed by command substitution inside `config_setup.sh`:

```bash
local_env_file=$(mgsnake local-env-path)
```

so the command prints the path and nothing else. Diagnostics go to stderr precisely so this stays
parseable at any log level.

### msg

Prints a message to the console in a custom format and logs it into the workspace configuration log file.

**Synopsis:** `mgsnake msg [OPTIONS] MESSAGE`

**Aliases:** `message`

| Option | Description |
| --- | --- |
| `-p, --prologue TEXT` | An optional starting message printed before the message. |
| `-e, --epilog TEXT` | An optional ending message printed after the message. |
| `-t, --type-msg [s\|i\|w\|e\|a\|t]` | The type of message to be printed:<br><br>'S' - Success<br><br>'I' - Information -- default<br><br>'W' - Warning<br><br>'E' - Error<br><br>'A' - Advice -- use for Debugging<br><br>'T' - Tip |
| `-h, --help` | Show this message and exit. |

- `message` — The message to print and log.

Exposes the internal logging mechanism to the shell. It exists so that the packaged shell scripts
(`config_setup.sh` / `config_setup.ps1`) print success, warning and error messages in exactly the
same format as the Python commands, instead of each one inventing its own `echo`.

#### Notes

The message is both printed to the console and written to the workspace log file.

### reload-config

Re-sources the local configuration file (and the environment file it loads) into the current shell session, so edits to it take effect without opening a new terminal.

**Synopsis:** `mgsnake reload-config [OPTIONS]`

| Option | Description |
| --- | --- |
| `-h, --help` | Show this message and exit. |

Applies edits to the local configuration file without opening a new terminal. Sourcing that file is
what makes its functions, aliases and exported variables available, and a shell only does it at
startup — so after editing it, the running session keeps the old definitions until something
re-sources it. This is that something.

#### Notes

A process cannot change the environment of the process that started it, which is a guarantee of the
operating system rather than a limitation of this tool. The command therefore does no work itself:
it reports the request through its exit status, and the `mgsnake` shell function installed by the
init script performs the sourcing inside the session that asked for it.

That function is the reason this works, so the command is only useful once
`config_setup.sh` / `config_setup.ps1` is sourced from the shell profile — see `shell-path`. Run
without it, the command exits with its status and nothing happens.

Once the shell has re-sourced the file the request is fulfilled, so the function reports success to
whoever called it. Only a direct invocation that bypasses the function (`command mgsnake
reload-config`) shows the raw status.

Commands that rewrite the local files (`working-env`, `set-java`, `set-gradle`, `set-maven`,
`init-local-config`) already emit the same request when they finish, so running this afterwards is
usually unnecessary. Reach for it after editing the file by hand.

Reloading the configuration file also reloads the environment file, because the generated
configuration file loads it on the way through.

### shell-path

Prints to stdout the path of the packaged shell initialization script (config_setup.sh or config_setup.ps1) to be sourced from the shell profile.

**Synopsis:** `mgsnake shell-path [OPTIONS] {bash|zsh|powershell|pwsh}`

**Aliases:** `sp`

| Option | Description |
| --- | --- |
| `-h, --help` | Show this message and exit. |

- `shell` — The shell to be initialized.

Add the matching line to your shell profile — this is what makes `mgsnake` shell integration active
in every new session.

#### Examples

For bash/zsh, in `~/.bashrc` or `~/.zshrc`:

```bash
. "$(mgsnake shell-path bash)"
```

For PowerShell, in your profile (`$PROFILE`):

```powershell
. (mgsnake shell-path pwsh)
```

#### Notes

Sourcing that script sets `MEGA_SNAKE_SHELL` and defines the private helpers behind `reload-config`
and `load-env`. Because the profile calls this command *before* that variable exists, it is the one
command that runs with no initialization at all — which is also why it prints the bare path and
nothing else.

It also defines `mgsnake` itself as a thin shell function around the real executable. That function
is what makes the environment auto-reload work: a command that rewrites one of the local environment
files exits with status `29`, and only the parent shell can act on it — a child process cannot
change its parent's environment. The function forwards every argument and calls the executable
through `command mgsnake` (or its resolved path on PowerShell), so there is no recursion. A served
`29`/`30` signal is reported to the caller as `0` once the function has carried it out — the signal
is a request, and propagating it would make every environment command look like a failure to a
`set -e` script or an `&&` chain; every other status passes through unchanged. The only visible
difference is that `type mgsnake` reports a function.
