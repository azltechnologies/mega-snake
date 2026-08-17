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

Reload it in the current session with `mgsnake_reload`, defined by the shell init script (see
`shell-path`).

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
| `-t, --target-hash TEXT` | Commit hash to compare up to, instead of the current HEAD. Forces --scope c, since the index and the working tree only exist for HEAD; combining it with another scope is rejected. |
| `-d, --delete-original-files` | Delete the generated copy of the original files in the diff tree |
| `-s, --scope [c\|s\|u]` | Changes to include: (c)ommitted only [default], committed and (s)taged, or also (u)nstaged and untracked. Only 'c' is compatible with --target-hash: the other two read the index and the working tree, which exist only for HEAD, so passing them together is rejected instead of silently ignoring one of them.  [default: c] |
| `-h, --help` | Show this message and exit. |

Useful for code reviews, progress comments on a ticket, and release notes: it answers "what did I
touch since master?" without scrolling through `git log`.

Both ends of the comparison move independently: `--origin-hash` sets where it starts, `--target-hash`
sets where it ends. With both, the range is fully explicit and no longer anchored to the current checkout,
which is what makes it possible to reconstruct a past release from the two commits that bound it.

#### Output

Writes three files to `workspace_temp/diff_tree/` and opens them in VS Code:

- `diff_tree.txt` — the visual tree of created, modified and deleted files.
- `diff_changes.txt` — the Git-style patch for those files.
- `diff_commit.txt` — the commit list (hash, date, message), newest first.

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

The output directory is wiped and recreated on every run. No remote is required: when the
repository has none, the comparison falls back to the current local branch.

`--target-hash` only applies to the committed scope (`--scope c`, the default). The staged and unstaged
scopes read the index and the working tree, which exist only for HEAD, so combining them is rejected
rather than silently ignoring one of the two.

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

Iterates over the remote branches asking the user which merged branches to delete

**Synopsis:** `mgsnake remote-branches-cleanup [OPTIONS]`

**Aliases:** `rbc`

| Option | Description |
| --- | --- |
| `-h, --help` | Show this message and exit. |

Consumes the report produced by `remote-branches-details` (and can re-run it first to refresh the
data), then deletes the branches you select and prunes the local references pointing at them.

Rather than passing objects between commands in memory, the two commands communicate through
`workspace_temp/remote_branches.txt`. That file is the point: you can inspect it — and edit it —
before running a destructive command against your remote.

#### Notes

It takes no options: run it and follow the prompts. Deletion is `git push origin --delete <branch>`
and cannot be undone from here. Requires a remote.

### remote-branches-details

Creates a detailed list of remote branches filtered by type

**Synopsis:** `mgsnake remote-branches-details [OPTIONS]`

**Aliases:** `rbd`

| Option | Description |
| --- | --- |
| `-f, --filter-by [m\|u\|a]` | filter branches by merge status against main branch:<br><br>'M' - merged branches<br><br>'U' - unmerged branches<br><br>'A' - all branches (default) |
| `-h, --help` | Show this message and exit. |

A branch counts as merged when it was merged, fast-forwarded, **rebased**, or **squashed** into the
main branch — the last two are detected by patch id, so branches that were squash-merged through a
PR are correctly reported as merged instead of lingering as unmerged noise.

Comparison is always against the remote main branch, never the possibly stale local copy.

#### Output

Creates `workspace_temp/remote_branches.txt` with per-branch details: author, last commit date, and
ahead/behind counts.

#### Notes

Requires a remote. Feed the output to `remote-branches-cleanup` to act on it.

## Light Weight

### create-release

Creates a GitHub release and tag: the new tag is the latest release's version with one of its components incremented, and the publication is delegated to the gh CLI.

**Synopsis:** `mgsnake create-release [OPTIONS] {p|r|l} [NOTES] [BRANCH]`

**Aliases:** `release`, `cr`

| Option | Description |
| --- | --- |
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
counter that grows so the same version can be built repeatedly. It is **rejected for the `l` type**:
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

The new tag is always derived from the release GitHub currently marks as `latest`, which is never a
pre-release. A release tagged by hand in the GitHub UI *can* hold that mark with any tag text, so the
command refuses to continue when that tag is not a `vX.Y.Z` version: there is nothing to increment.
Publish a version-tagged release first, or create that one with `gh release create`. It also refuses when the derived
tag already exists, which means the repository holds a tag without a matching release.

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

### get-local-config-path

Prints to stdout the path of the local configuration file (.sh or .ps1 depending on the active shell).

**Synopsis:** `mgsnake get-local-config-path [OPTIONS]`

**Aliases:** `lcp`

| Option | Description |
| --- | --- |
| `-h, --help` | Show this message and exit. |

Resolves the local configuration file created by `init-local-config`, picking the `.sh` or `.ps1`
variant according to the active shell.

#### Notes

Its stdout is consumed by command substitution inside `config_setup.sh`:

```bash
local_config_file=$(mgsnake get-local-config-path)
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

Sourcing that script sets `MEGA_SNAKE_SHELL` and defines `mgsnake_reload`. Because the profile calls
this command *before* that variable exists, it is the one command that runs with no initialization
at all — which is also why it prints the bare path and nothing else.
