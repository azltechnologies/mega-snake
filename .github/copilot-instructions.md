# GitHub Copilot Instructions for `unix-scripts` (Mega Snake)

## 1. Project Overview & Philosophy

`mega_snake` is a robust Python 3.13+ CLI tool designed to standardize the local development lifecycle. It acts as a "Swiss Army Knife" for developers, primarily automating the complex configuration of VS Code environments for Java/Gradle, but extending into Git management, Release orchestration context, and Google Cloud observability.

**Core Philosophy:**
- **Zero Config Start**: A developer should be able to run `mgsnake working-env` and have a fully functional IDE state immediately.
- **Idempotency**: Commands should be safe to run multiple times without destructive side effects unless explicitly requested.
- **System Integration**: The tool deeply integrates with the OS shell (Bash/Zsh/PowerShell) and external tools (Git, Java, Gradle).

**Tech Stack:**
- **Runtime**: Python 3.13+
- **CLI Framework**: `click` (Command composition), `rich-click` (Beautiful help text/formatting)
- **UI/Output**: `colorama` (Terminal colors), `rich` (Tables/Trees)
- **Dependency Management**: `uv`
- **Shell Interop**: Custom shell scripts (`config_setup.sh/ps1`) that wrap the python execution.

---

## 2. Architecture & Patterns

### 2.1 Entry Point & CLI Orchestration (`src/mega_snake/__main__.py`)

The application uses a `click.Group` with a custom `CliGroup` class to support command aliases. The entry point `cli()` function initializes global application properties before any command runs.

**Critical Pattern: Initialization flags (`no_init` and `skip`)**
Before invoking a subcommand, `cli()` reads the metadata attached by `@cli_metadata(...)` and decides *how much*
initialization to run. There are exactly **three** initialization levels, driven by two flags:

| Flag | Level | `init_app_properties` | Use it when |
|---|---|---|---|
| *(none)* | **Full** | Called; `working_path` must exist or the command fails | The command needs a valid workspace (`set-java`, `set-gradle`, …) |
| `skip` | **Light-weight** | Called with `light_weight=True`; a missing `working_path` is tolerated | The command can run anywhere, but still wants properties/logging when available (`create-release`, `diff-tree`, …) |
| `no_init` | **None** | **Never called** — `cli()` returns early | The command must work *before* the environment exists at all (`shell-path`) |

```python
# src/mega_snake/__main__.py
@click.pass_context
def cli(ctx: click.Context, log_level: str) -> None:
    # ...
    metadata = getattr(cmd.callback, ATTR_METADATA, {})   # ATTR_METADATA == "flags"
    flags: Optional[set[str]] = metadata.get(META_FLAGS)  # META_FLAGS   == "flags"
    if flags and "no_init" in flags:
        return                      # No AppProperties at all, and no MEGA_SNAKE_SHELL check
    ws_advice(f"Invoking subcommand: {cmd_name}")
    if flags and "skip" in flags:
        light_weight = True         # AppProperties built, working_path validation deferred
    # ...
    init_app_properties(log_level, shell, light_weight)
```

**Note the double nesting**: `cli_metadata(**metadata)` stores its kwargs under the callback's `flags` attribute, so
`@cli_metadata(flags={"skip"})` produces `callback.flags == {"flags": {"skip"}}`. That is why the entry point reads
`metadata.get("flags")` and not `metadata` directly. `wrapper_decorator.update_flags` propagates these from both the
module wrapper *and* the command callback onto the wrapping command, which is what makes a module-level
`@cli_metadata(flags={"skip"})` apply to every command in the module.

**When `no_init` is the only option**
`no_init` exists for the **bootstrap problem**, not as a "lighter light-weight". Full and light-weight initialization
both require `MEGA_SNAKE_SHELL`, and `cli()` raises `EnvironmentError` when it is unset. But that variable is exported
by `config_setup.sh`, and the user's shell profile has to run `mgsnake shell-path bash` *to find that script in the
first place* — so at that moment the variable does not exist yet. Returning early is the only way `shell-path` can
answer. Consequences for any `no_init` command:

- `AppProperties` is never constructed: `get_property()`, `working_path`, `log_file` and the `.code-workspace` are all
  unavailable. Depend only on `importlib.resources` and the arguments.
- Nothing is logged to file, and the `ws_*` helpers are pointless — `shell-path` deliberately uses `click.echo` because
  its stdout is consumed by command substitution (`. "$(mgsnake shell-path bash)"`) and must stay clean.

**Keep `no_init` stdout clean.** Anything a shell captures with `$(...)` must print *only* the value. `ws_advice` is
level-gated (it checks `logger.level`), so it is silent when logging was never configured — but that is a property of
the current initialization order, not a guarantee. Never add unconditional `ws_*` output to a command whose stdout is
consumed by a script.

**What light-weight mode (`skip`) actually defers**
When `working_path` (e.g. `workspace_temp`) is missing, `AppProperties.__init__` raises `FileNotFoundError` *after* setting
`resources_path`, `working_path`, `local_config_file`, `local_env_file`, `shell` and a best-effort `workspace_file`.
`init_app_properties` swallows that error when `light_weight=True`, which leaves **unset**: the `_log_level` attribute,
`log_file`, `graphql_schema_file` and the `__post_init__` validation — and skips `formatting.config_log`, so nothing is
written to the log file and `--log-level DEBUG` has no effect (`ws_advice` checks `logger.level`).

Console output is unaffected: every `ws_*` helper in `formatting.py` calls `print()` **before** `logger.*`, so the tool
always talks to the user regardless of whether logging is configured. That is the decoupling light-weight mode relies on.

**Completing a deferred initialization (`complete_app_properties`)**
Commands that are light-weight but *do* need the working path (see the pre-flight wrappers below) call
`complete_app_properties()` right after securing the folder. It finishes exactly where `__init__` stopped
(`_log_level`, `log_file`, `graphql_schema_file`, `config_log`) and is idempotent, so it is a no-op after a full
initialization. `_check_forbidden_execution` treats `complete_initialization` as part of the initialization
(`INITIALIZATION_METHODS`), which is what allows the init-only validators to run from there.

**Rule of thumb:** a command may be light-weight *and* depend on `working_path` only if its wrapper offers to create the
folder and fails with a clean `click.ClickException` when the user declines. Never let it reach the command body without it.

### 2.2 Command Registration & Aliases (`src/mega_snake/util/cli_group.py`)

We do not standard `click` alias implementation. We use `CliGroup` to register commands with multiple names.

**Usage:**
```python
# Registration in __main__.py
from .diff_tree.module import main as diff_tree
# Registers 'diff-tree' command accessible via 'dt' and 'tree' aliases
cli.add_command_with_alias(diff_tree, ["dt", "tree"])
```

**How an alias actually works.** `add_command_with_alias` does two things: it stores the alias list on the real
command under the `aliases` attribute, and it registers one extra `click.Command(hidden=True)` per alias so
`mgsnake dt` resolves. Both facts matter downstream:

- **rich-click reads the `aliases` attribute natively.** The alias column you see in `mgsnake --help` (the green one
  next to each command) is drawn by rich-click's `_get_command_aliases_help`, styled with `style_command_aliases`
  and positioned by `commands_table_column_types`. Nothing in this repo renders it. If you ever need to change how
  that panel looks, the knobs are in the rich-click configuration, **not** in a `format_commands` override —
  `RichGroup` overrides `format_help()` to call its own `rich_format_help()`, so Click's classic
  `format_help → format_commands` path is never taken (and `RichHelpFormatter.write_dl` is a stub that only emits a
  `RuntimeWarning`).
- **Hidden alias commands must be skipped when enumerating commands.** A naive walk of `cli.commands` yields three
  entries for `diff-tree` (itself plus `dt` and `tree`). Use `iter_documented_commands()` (§3.7), which filters
  `cmd.hidden` and folds the aliases back in.

**Attribute constants.** `cli_group.py` owns the names of every custom attribute the CLI hangs on commands and
callbacks. Import them instead of writing the string literal:

| Constant | Value | Meaning |
|---|---|---|
| `ATTR_METADATA` | `"flags"` | Attribute where `@cli_metadata` stores **all** its kwargs. |
| `META_FLAGS` | `"flags"` | Metadata **key** holding the initialization flags (`skip` / `no_init`). Same string as above, different role — this is the "double nesting" explained in §2.1. |
| `ATTR_ALIAS` | `"aliases"` | The alias list, read by rich-click and by the docs iterator. |
| `ATTR_DOCS` | `"docs_fragment"` | Overrides the fragment filename (defaults to the command name). |
| `ATTR_GROUP` | `"docs_group"` | Overrides the documentation group title (see §3.7). |

`CliGroup.add_command` resolves `ATTR_DOCS`/`ATTR_GROUP` onto the command at registration time, so every command has
them by the time anything iterates the registry.

**Group title resolution is decided by provenance, never by the shape of the string.** An explicit title (set via
`@cli_metadata(docs_group=...)` or already present on the command) is used **verbatim**; only a title *derived* from
the module path is reformatted with `.title()`, because there the raw value is an identifier like `remote_branches`.
Do not reintroduce heuristics such as "if it contains a space it must already be a title" — `docs_group="GraphQL"`
would silently become `"Graphql"`.

### 2.3 The Wrapper Pattern (`module.py` files)

Each functional module (e.g., `config_environment`) exposes an `add_wrapper` decorator. This allows module-specific checks to run before the command execution, keeping the core logic clean.

**Example from `src/mega_snake/config_environment/module.py`:**
```python
def wrapper(_ctx: click.Context, *_args, **_kwargs) -> None:
    # Pre-flight check: verify we're in a valid workspace
    if not get_workspace_folder():
        raise RuntimeError("Not in a valid workspace.")

add_wrapper = wrapper_decorator(wrapper) 

# Usage in __main__.py
for command in config_environment.commands.values():
    # Wraps every command in the module with the pre-flight check
    cli.add_command(config_environment_result_callback(command))
```

**Educational Logic:**
This implements the **Decorator Pattern**. Instead of repeating validation logic in every command, we define it once in the wrapper. The `__main__.py` entry point applies this wrapper dynamically when registering commands, ensuring checks only run when a relevant command is invoked.

**Custom attributes must be preserved across wrapping.** `wrapper_decorator` rebuilds the command from
`click.Command.__init__`'s signature, so **anything not in that signature is dropped** unless it is copied by hand.
That copying is centralized in a `preserved_attrs` tuple plus `apply_command_metadata()`:

```python
# src/mega_snake/util/util.py
preserved_attrs: tuple[str, ...] = (ATTR_ALIAS, ATTR_DOCS, ATTR_GROUP)
# ...copied from the original command, then from the module wrapper, then from the command callback
```

If you ever add a new custom attribute, **add it to that tuple** — otherwise it will vanish silently at registration
and the failure will only show up much later (e.g. a command landing in the wrong documentation group).

---

## 3. Core Functional Modules

### 3.1 Environment Configuration (`src/mega_snake/config_environment/`)

This is the most complex module, responsible for generating `.code-workspace` files. It configures the "settings" section of the workspace file directly, avoiding reliance on `.vscode/settings.json`.

#### `working-env`
- **Logic**: 
    1. Validates Git repository status.
    2. Loads local developer overrides (`initial_load`).
    3. Configures Java (`set-java`) and Gradle (`set-gradle`).
    4. Generates VS Code tasks, launch configurations, and recommendations.

#### `set-java` (`java_set.py`)
Manages the `java.configuration.runtimes` and `terminal.integrated.env` settings in VS Code.

**Key Logic:**
- It parses the `.code-workspace` file (as JSON with comments).
- It queries the OS for installed JDKs.
- It updates the `settings` structure inside the workspace file to point `JAVA_HOME` to the selected version.

```python
# src/mega_snake/config_environment/java_set.py
ENV_VARIABLE = f"terminal.integrated.env.{OS_MAP[OS]}"
JAVA_JQ_QUERY = f'.settings["{ENV_VARIABLE}"].JAVA_HOME'

# It uses python logic to traverse the JSON structure similar to JQ
# to find and replace the Java path.
```

#### `set-gradle` (`gradle_set.py`)
Like `set-java`, this configures the Gradle version for the workspace.

**Key Logic:**
- It identifies installed Gradle versions via `ToolVersion` abstraction.
- It updates `java.import.gradle.home` and `terminal.integrated.env` settings.
- It ensures consistency between the terminal environment and the IDE's internal Gradle wrapper.

**Technical Note: JSON with Comments**
Both `set-java` and `set-gradle` modify the `.code-workspace` file which contains comments. The standard python `json` library fails on comments. We use a custom `load_json_with_comments` utility to handle VS Code's configuration format safely without stripping comments, which are vital for developers understanding the config.

#### `init-local-config` (`local_config.py`)
Creates a local developer-specific configuration file that is **ignored by Git**.

**Why?**
Developers often have machine-specific tokens, paths, or aliases that shouldn't be committed to the repo. `init-local-config` generates a shell-specific file (`.sh` or `.ps1` logic embedded) that is sourced by the main environment. This pattern allows the tool to support "Convention over Configuration" while still allowing for "Configuration" when necessary.

### 3.2 Git Utilities (`src/mega_snake/diff_tree/`)

#### `diff-tree` (`dt`)
Generates a visual tree representation of changed files.

**Module layout** (same shape as every other module): `diff_tree/diff_tree.py` holds the command and its helpers,
`diff_tree/module.py` holds the `CliGroup`, the pre-flight `wrapper` (carrying the `skip` flag) and `add_wrapper`.
`__main__.py` registers it by iterating `diff_tree.commands.values()` and wrapping each one, so the aliases go through
the same pre-flight check as the command.

**Implementation Details:**
- **Both ends of the comparison are movable.** `-o | --origin-hash` replaces the base (master by default) and
  `-t | --target-hash` replaces the far end (HEAD by default); `_validate_commit` is shared by both, so a reference
  that resolves to a tree or a blob is rejected before any diff runs. `--target-hash` is refused for the `s`/`u` scopes:
  those read the index and the working tree, which exist only for HEAD, so honouring the flag is impossible and
  ignoring it silently would misreport the range. That check runs **before** the output directory is wiped, so a
  rejected invocation never destroys the previous run's files.
- Uses `git diff --raw --no-renames {diff_target}` to get raw file lists. `_get_diff_target` builds `diff_target`
  from the `-s | --scope` flag, which selects how much of the work is included: `c` (default, committed only) →
  `{main_branch} {current_branch}`, `s` (committed + staged) → `--cached {main_branch}`, `u` (committed + staged +
  unstaged) → `{main_branch}`. Rename detection is disabled so the raw output keeps one entry per path in every scope,
  which is what the tree reconstruction expects.
- Untracked files are invisible to `git diff`, so `_get_untracked_files` adds them (via
  `git ls-files --others --exclude-standard`) as `FileType.ADDED` — for the `u` scope only.
- The same `diff_target` drives the binary-file detection (`git diff --numstat`) and the `diff_changes.txt` patch, so
  the three outputs always describe the same set of changes.
- `diff_commit.txt` cannot follow `diff_target` (uncommitted work has no commits), so `_get_pending_changes_report`
  prepends the pending files to it instead: `Unstaged files:` (`git diff --name-only` plus the untracked ones) and
  then `Staged files:` (`git diff --cached --name-only`), each one only when the scope covers it **and** it has
  files. Sections go above the newest commit, keeping the whole file newest-first.
- categorizes files using `FileType.from_symbol(symbol)`.
- Reconstructs a dummy directory structure in `workspace_temp/diff_tree_dummy_repo`.
- Uses `directory_tree` library to generating the visual text tree.
- The output directory is wiped (`shutil.rmtree`) and recreated (`os.makedirs`) on **every** run, so no file write
  depends on a directory left behind by a previous run.
- No remote is required: `get_main_branch` falls back to the current local branch, so its wrapper only calls
  `ensure_working_path()` + `complete_app_properties()`.

```python
# src/mega_snake/diff_tree/diff_tree.py
for diff in diff_str.split("\n"):
    columns: list[str] = diff.split("\t")
    symbol = columns[0].split(" ")[4] # M, A, D, etc.
    path: str = columns[1]
    # builds tree structure...
```

### 3.3 Remote Branch Management (`src/mega_snake/remote_branches/`)

#### `remote-branches-details`
Analyzes remote branches to suggest cleanup candidates.

**Filtering Logic (`-f` flag):**
- **'M' (Merged)**: Branches that have been merged into `master`.
- **'U' (Unmerged)**: Branches with unique commits not in `master`.
- **'A' (All)**: Both.

**Merge detection (`RemoteBranch.from_branch`)** — a branch counts as merged when *any* of these holds, checked in
order and against `remotes/{remote}/{main_branch}` (never the possibly stale local branch):
1. **Ancestry**: `git branch -a --contains <tip>` lists the main branch. Only catches real merges and fast-forwards.
2. **Rebase merge** (`_is_rebase_merged`): `git cherry <main_ref> <branch>` marks **every** branch commit with `-`,
   meaning each one is already applied on main by patch id under a different hash.
3. **Squash merge** (`_is_squash_merged`): the branch tree is turned into a synthetic commit parented on the
   merge-base (`git commit-tree`), so it carries the same combined patch id as the squashed commit, and `git cherry`
   is asked about that one commit.

Steps 2 and 3 are **not** interchangeable: a rebase replays the commits individually, so no single commit on main
matches the combined diff; a squash collapses them, so none of the originals matches. Checking only one of the two
silently misses the other style. Both are skipped when there is no merge-base, and for the main branch itself.

It creates `workspace_temp/remote_branches.txt` containing detailed metadata (author, last commit date, ahead/behind count) for every branch.

#### `remote-branches-cleanup`
An interactive tool that consumes the output of `remote-branches-details`.

**Logic:**
1. Allows re-running `remote-branches-details` to refresh data.
2. Reads `workspace_temp/remote_branches.txt`.
3. Presents an interactive list to the user to select branches for deletion.
4. Performs `git push origin --delete <branch>` and prunes local references.

**Design Pattern: Pipeline via Files**
Instead of passing complex objects between commands in memory, we use the filesystem (`remote_branches.txt`) as an intermediate buffer. This allows the user to inspect (and potentially edit) the list of candidates before running the destructive cleanup command.

**Pre-flight wrapper (`remote_branches/module.py`)**
Both commands are light-weight (`skip`) but need a remote and the working path, so the wrapper runs
`require_remote()` → `ensure_working_path()` → `complete_app_properties()`. The commands themselves still call
`require_remote()`; because `get_remote()` is memoized, that costs no extra `git remote` and no second prompt.

### 3.4 Release Management (`src/mega_snake/light_weight/create_release.py`)

Automates GitHub releases, creating tags and proper GitHub Release entries.

**Arguments:**
- `tag_suffix`: e.g., `v1.0.0-{suffix}`
- `release_type`:
    - `p`: Prerelease (`--prerelease`)
    - `l`: Latest (`--latest`) — asks for confirmation before creating a new latest release
    - `r`: Regular release (`--latest=false`) — publishes **without** taking the `latest` mark; if GitHub moves the
      `latest` pointer anyway, the command restores it to the previous latest release

The three types are explained in prose in `resources/docs/create-release.md` (by their *effect* — which version
users land on — not as a flag list, since the synopsis already shows `{p|r|l}`). The `epilog=` documents only the
positional arguments, per §3.7.

**Logic:**
It fetches the current tags, calculates the new tag based on the suffix, and relies on the `gh` CLI to publish the release.

**Technical Note: Why use the `gh` wrapper?**
We use the `gh` (GitHub CLI) tool because it leverages the user's existing authentication state, avoiding the need to manage complex API tokens within the Python code.

```python
    # src/mega_snake/light_weight/release_handler.py
    cwd: str = (
        f'gh release create {tag_name} {release_type} --target "{release_branch}" '
        f'--title "{tag_name}" {release_notes} --generate-notes'
    )
```

**Educational Logic:**
Instead of re-implementing the GitHub API client (which requires managing OAuth tokens, permissions, etc.), we delegate the heavy lifting to the `gh` binary. This is a common "shell wrapper" pattern where Python manages the *control flow* and *validation*, but the shell executes the *remote action*.

### 3.5 Dependency Vulnerability Audit (`src/mega_snake/dependency_audit/`)

#### `scan-dependencies` (`sdep`, `audit`)
Scans the project's locked dependencies for known vulnerabilities, across multiple ecosystems, and files a GitHub
issue per new finding.

**Logic:**
1. `scanner.py` defines a `DependencyAuditor` protocol (`scan() -> list[Vulnerability]`) with two implementations:
   - `PipAuditAuditor`: exports `uv.lock` to a requirements file (`uv export`) and runs `pip-audit` against it
     (Python/uv projects).
   - `OsvScannerAuditor`: runs `osv-scanner --format json --recursive <target>` (Java/Gradle/Maven, Node, and as the
     generic fallback for any other ecosystem). Chosen over one tool per ecosystem because it already reads the same
     OSV advisory database `Vulnerability.advisory_url` relies on.
   - Both parse their tool's JSON output into the same `Vulnerability` objects (package, installed version, fix
     versions, aliases/CVEs, description).
   - `detect_ecosystem()` picks the auditor from marker files: `uv.lock` → Python, `build.gradle(.kts)`/`pom.xml` →
     Java, `package-lock.json` → Node, otherwise falls back to the generic `OsvScannerAuditor`. `get_auditor()` /
     `scan_dependencies()` accept an explicit `ecosystem` override.
2. `issue_manager.py` builds a deterministic issue title per finding, checks `gh issue list --search` for an existing
   issue with that exact title (open or closed) to avoid duplicates, and files a new one via `gh issue create`
   otherwise. It is ecosystem-agnostic — it only consumes `Vulnerability` objects — and is unaffected by the
   ecosystem the finding came from.
3. `module.py` wires this into the `scan-dependencies` command (`--dry-run` prints findings without creating issues;
   `--ecosystem python|java|node|osv` forces the auditor instead of auto-detecting it).

**Design Pattern:** Same "shell wrapper" pattern as `create-release` — Python owns control flow/parsing, `gh` (and
`pip-audit`/`osv-scanner`) own the remote/scanning action.

**Automation:** Enabled via Dependabot (`.github/dependabot.yml`, PRs for outdated deps) plus a scheduled/PR GitHub
Actions workflow (`.github/workflows/dependency-scan.yml`) that runs `mgsnake scan-dependencies`. Both files are
inherently per-repo (GitHub reads them from the repo where they live), so consuming repos on other ecosystems must
still add their own copies (adapted to install the right auditor, e.g. `osv-scanner`), even though the scanning logic
itself is consumed from `mega-snake`.

### 3.6 Other Utilities

#### `graphql-schema` (`graphql_schema.py`)
Compiles multiple `.graphql` files into a single schema and generates introspection JSON.

**Why introspection?**
Frontend tools (like Apollo) and IDE plugins often require a full introspection result (`schema.json`) to provide autocompletion and type checking, not just the raw SDL string.

#### `expired-certs-jks` (`jks_expired_certs.py`)
Audits Java KeyStore (JKS) files for expired certificates using `keytool`.

**Technical Challenge:**
Parsing the output of `keytool -v -list` is non-trivial because the date format depends on the system locale and standard Java output formats. The tool attempts to parse these formats to warn developers before their local dev environments break due to expired SSL certs.

#### `msg` (`echo.py`)
Exposes the internal logging mechanism to the shell. Used by `config_setup.sh` to print consistent success/error messages from shell scripts.

### 3.7 Command Reference Generation (`src/mega_snake/docs_gen/`)

#### `generate-docs`
Generates `COMMANDS.md` — the full command reference — by introspecting the live Click objects and appending the
hand-written fragments from `resources/docs/` (§6.3).

**The governing principle:** every fact lives in exactly one place. Whatever the program already knows (synopsis,
options, types, defaults, aliases, grouping) is **generated** and cannot drift. Whatever only a human knows (why the
command exists, what it writes to disk, the caveats) is **hand-written** in a fragment. Neither half may restate the
other, and two tests enforce it (§6.3).

**Module layout** (same shape as every other module):

| File | Responsibility |
|---|---|
| `docs_gen/introspect.py` | Walks the CLI and normalizes it into `IntrospectedCommand` dataclasses. Owns `normalize_help()` and `normalize_epilog()`. |
| `docs_gen/markdown_writer.py` | Pure rendering: dataclasses → Markdown. Owns the table-escaping helpers and `write_or_check_document()`. |
| `docs_gen/generate_docs.py` | The `generate-docs` Click command only. |
| `docs_gen/man_page.py` | The `man` Click command: alias resolution, terminal rendering, paging. |
| `docs_gen/module.py` | The `CliGroup`, the `wrapper` (carrying `docs_group="Documentation"`) and `add_wrapper`. |

`generate-docs` is `@cli_metadata(flags={"no_init"})`: it needs no workspace, no git and no `MEGA_SNAKE_SHELL`, so it
resolves the packaged fragments through `importlib.resources` and must never call `get_property()`. It imports the
root `cli` **lazily inside the function**, because `__main__` imports this module to register the command.

**Flags:** `--output PATH` (default `COMMANDS.md`) and `--check` (render in memory, diff, exit non-zero when stale).
`--check` compares with `splitlines()` and writes with `newline="\n"`, so CRLF/LF differences never cause a false
failure on Windows.

#### `man`

Pages the same reference in the terminal — the whole document, or one command when `mgsnake man [COMMAND]` names one.
Also `no_init`, and it imports the root `cli` lazily for the same reason.

**It renders in memory; it never reads `COMMANDS.md`.** That file is committed to the repository but is *not* shipped
in the wheel (`packages = ["src/mega_snake"]` only sweeps in the package tree, and `COMMANDS.md` sits at the repo
root). Reading it would produce a command that works in a source checkout and fails for every installed user — the
exact class of bug that never shows up in development. The fragments *are* packaged, so introspection plus
`importlib.resources` is the only source that exists in both environments.

**Nothing is installed to `/usr/share/man`.** `uv tool install` and `pipx` create an isolated environment and copy
nothing to the system man path, so `man mgsnake` cannot resolve. Paging from inside the CLI is also the only form
that works on PowerShell, where `man` does not exist.

Four details that are easy to get wrong when touching this command:

- **Paging is wrapped in a fallback, and the fallback is load-bearing.** `click.echo_via_pager` raises `TypeError` on
  the interactive Windows path of click 8.4.x: `_pager_contextmanager` picks `_tempfilepager`, which yields a binary
  `NamedTemporaryFile`, and `get_pager_file` only wraps a stream exposing a `.buffer`, so `str` reaches a binary
  handle. There is no fixed click release (8.4.2 is the latest) and pinning backwards drops below what rich-click
  resolves, so `_page_or_echo` catches `TypeError`/`UnicodeEncodeError` and prints plainly instead. **Catch only those
  two** — widening it hides real failures, and a test pins that. Do not "cover" this with a `# pragma`: the regression
  test forces click's Windows context manager on any platform, which is the only honest way to exercise it.
- **`<br>` must be folded back into spaces before rendering, in table rows only.** The Markdown writer emits
  `CELL_LINE_BREAK` so multi-line option help survives a table row; rich drops HTML tags outright, which would glue
  the choice lists of `--type-msg` and `--filter-by` into one unreadable run. Folding the whole document instead would
  also rewrite a literal `<br>` a human wrote in fragment prose or inside a fenced code block. Import the constant,
  never the literal.
- **Aliases resolve to the real command, and never shadow one.** The hidden alias commands are separate click objects
  that `iter_documented_commands()` skips, so `man dt` maps `dt` → `diff-tree` through the `ATTR_ALIAS` list rather
  than looking the alias command up. Real names are seeded into the lookup first and aliases only `setdefault` into
  the gaps: several existing aliases (`audit`, `release`, `env`, `tree`) are plausible names for a future command, and
  without that precedence whichever entry came last would win.
- **ANSI is emitted unconditionally** (`Console(force_terminal=True)`). Click's pager strips it again when the pager
  cannot display color, so this keeps the styling where it works without breaking where it does not.

Rendering reuses `render_markdown()` on a filtered command list rather than adding a second rendering path — a
single-command page is the same document with one entry, which is what keeps the two outputs from drifting apart.

#### Document structure (heading levels)

`COMMANDS.md` is one document with a strict four-level hierarchy. **A fragment writes `##`, and the generator
re-emits it as `####`** — so a fragment section always ends up nested under its command, never beside it:

```text
# Available Commands          <- the document title (one per file, emitted by the writer)
## Config Environment         <- a documentation group (from docs_group / the module name)
### set-java                  <- a command name (plain, no backticks)
#### Output                   <- a section of that command's fragment, promoted from its own '##'
#### Notes
### set-gradle                <- the next command, back at level 3
## Git & Release Management   <- the next group, back at level 2
```

| Level | What lives there | Written by |
|---|---|---|
| `#` | Document title (`# Available Commands`) | The writer (`GROUP_HEADING`) |
| `##` | Documentation group | The writer, from `docs_group` |
| `###` | Command name | The writer, from the registered command name |
| `####` | Fragment sections (`Output`, `Examples`, `Notes`) | **You**, as `##` in the fragment file |

So: **never write `###` or `####` in a fragment to start a section.** Write `##` and let
`_render_fragment()` shift it down. Getting this wrong makes a fragment section outrank the command it documents,
which silently breaks the document outline (and any tooling that builds a table of contents from it). Two tests
pin it: `test_generate_docs_renders_fragment_sections_below_the_command_heading` and
`test_fragment_sections_never_outrank_their_command`.

#### The fields the generator consumes — and what belongs in each

This is the contract every command must satisfy. **When adding or changing a command, walk this table top to bottom.**

| # | Source | Rendered as | What to put there |
|---|---|---|---|
| 1 | `short_help=` | *(not in `COMMANDS.md`)* — the description column of `mgsnake --help` | One line, under ~60 chars, verb-first ("Creates a new release on GitHub…"). It is what a user scanning the command list reads. |
| 2 | `help=` | The paragraph under the command heading | **Mandatory and explicit.** One or two sentences saying what the command does and, when it is not obvious, *how*. Never omit it: Click would fall back to the callback docstring and publish a "Parameters: …" block into the reference. A test enforces this. |
| 3 | *(derived)* | `**Synopsis:** mgsnake <cmd> [OPTIONS] ARGS` | Nothing to write — generated from `Command.get_usage()`. Never restate it by hand. |
| 4 | `aliases` | `**Aliases:** ...` | Set through `add_command_with_alias`. Prefer short, memorable aliases; they are the daily-use form. |
| 5 | option `help=` | The options table | **The single source of truth for every flag.** Put the *full* explanation here, including allowed values and what each one means. This is the field to enrich when a flag is hard to understand — not the epilog. |
| 6 | `show_default=True` | `[default: x]` in the table | Use it whenever a default is meaningful to the reader (e.g. `--password` defaulting to `changeit`). Cheaper and drift-proof compared to writing the default into the help text. |
| 7 | `epilog=` | A bullet list / paragraph after the table | **Positional arguments only** (Click never tabulates them) plus anything genuinely extra. See the rules below. |
| 8 | `resources/docs/<cmd>.md` | The prose after everything else | The "why", outputs on disk, examples and caveats (§6.3). |
| 9 | `docs_group` | The `##` section grouping commands | Optional; defaults to the module name titled. Set it when the module name is not a good public title. |

**Rules for `epilog=` (important, this is the subtle one).** Epilogs in this repo predate the generator, and used to
re-document by hand what is now generated. `normalize_epilog()` therefore **drops** any paragraph that is:

- a `usage:` line (the synopsis already says it),
- an `OPTIONS:` / `Args:` / `allowed values:` header,
- an entry starting with a flag **that the command actually declares** (the options table already says it).

The detection is anchored on the command's real `click.Option` objects, not on the paragraph's shape, so it cannot
drift. What survives — and what you should write there — is the **positional argument documentation**, in the form
`name: type - description`, one per paragraph. The writer turns those into a bullet list and strips the type
annotation, since the synopsis already shows which arguments exist:

```python
epilog="""
usage: mgsnake create-release <tag_suffix> <release_type> [notes] [branch]\n
Args:\n
    tag_suffix: str - suffix to add to the tag\n
    branch: Optional[str] - branch to create the release from. Default is the current branch.
"""
```
→ renders as `- \`tag_suffix\` — suffix to add to the tag`

**Never move detail out of an option `help=` into an epilog.** If a flag needs a long explanation, the explanation
belongs in field #5, where both `--help` and `COMMANDS.md` show it. An epilog that documents a flag is dropped, so
that detail would be lost from the reference entirely.

#### Text normalization (why the output is clean Markdown)

Click/rich help strings carry `\b` markers, manual `\n` wrapping and leading indentation. Two normalizers handle it:

- `normalize_help()` — strips `\b`, dedents, and collapses each paragraph's manual line breaks into one line while
  keeping blank-line paragraph separation.
- Table cells get extra treatment, because a Markdown table row **ends at the first newline** and is split on `|`
  *before* any inline parsing:
  - `_to_single_cell_line()` folds newlines into `<br>` (this is what keeps the multi-line choice lists of
    `--filter-by` and `--type-msg` from tearing the table apart);
  - `_escape_markdown_cell()` escapes `\` and `|` for prose cells;
  - `_render_code_cell()` renders option signatures as inline code: it escapes `|`, leaves backslashes **literal**
    (a code span does not interpret escapes, so doubling them would print `\\`), and grows the backtick fence past
    the longest backtick run in the text.

#### Introspection context (a real trap)

`click.Context.__init__` does **not** read a command's `context_settings`; only `Command.make_context()` does. The
synthetic contexts used for introspection therefore pass them explicitly:

```python
parent_ctx = click.Context(root, info_name=APP_NAME, **root.context_settings)
return click.Context(command, info_name=command_name, parent=parent_ctx, **command.context_settings)
```

Without this the generator documents a CLI the user does not have (`--help` instead of `-h, --help`, since the root
group declares `help_option_names=["-h", "--help"]`), and worse, the output becomes **dependent on the entry point**:
Click caches the help option per command, so a command already invoked in-process would render differently than one
that was not. A test pins the expected `-h, --help` rendering.

#### Determinism

`iter_documented_commands()` sorts explicitly by `(group.casefold(), name)`. Never emit output by iterating a `set`
(e.g. `flags={"skip"}`) or by relying on registration order in `MODULES` — the generated file is committed and diffed
in CI, so any instability turns into spurious failures.

---

## 4. Utilities & Helpers

### 4.1 Output Formatting (`src/mega_snake/util/formatting.py`)

** STRICT RULE**: NEVER use `print()`. Always use valid logging/formatting functions.

- `ws_info(msg)`: ℹ️ Blue info message.
- `ws_success(msg)`: ✅ Green success message.
- `ws_warning(msg)`: ⚠️ Yellow warning.
- `ws_error(msg)`: ❌ Red error.
- `ws_advice(msg)`: 💡 Helpful tip/advice.

### 4.2 Property Management (`src/mega_snake/util/props.py`)

Configuration is layered:
1. **Hardcoded Defaults**
2. **`src/config.properties`**: Static project config (versions, default paths).
3. **Local Overrides**: A local file (usually ignored by git) that overrides specific keys for a specific developer machine.

Access properties via `get_property(key)`.

**Note:** `no_init` commands (§2.1) cannot use any of this — `AppProperties` is never built for them. They must
resolve packaged files through `importlib.resources` and the constants below instead.

### 4.2.1 Package Constants (`src/mega_snake/constants.py`)

Shared literals live here; **never hardcode these strings**. Relevant to packaged-resource lookups:

| Constant | Value | Used for |
|---|---|---|
| `APP_NAME` | `"mgsnake"` | The user-facing command name (help text, synopsis). |
| `MODULE_NAME` | `"mega_snake"` | `importlib.resources.files(MODULE_NAME)` — the package root. |
| `RESOURCES_DIR` / `DOCS_DIR` | `"resources"` / `"docs"` | The packaged docs fragment directory. |
| `DOCS_FILE_SUFFIX` | `".md"` | Fragment file extension. |
| `DOCS_OUTPUT_FILE` | `"COMMANDS.md"` | Default target of `generate-docs`. |

Command-local literals (e.g. `CONFIG_SCRIPT` in `shell_init.py`, `GROUP_HEADING` in `markdown_writer.py`) stay in
their own module — `constants.py` is for values shared across modules.

### 4.3 Shell Execution (`src/mega_snake/util/util.py`)

Use `run_operation` for ALL shell commands. It handles logging, error capturing, and return codes.

```python
result = run_operation(
    command="git fetch --all", 
    message="Fetching remotes" # This is logged to console/file
)
if result.returncode != 0:
    # handle error...
```

**Shared helpers — always reuse these, never reimplement them:**

| Helper | Use it for |
|---|---|
| `get_remote()` | The repository's remote. **Memoized per process**: one `git remote`, and with several remotes the user is prompted only once no matter how many call sites ask. Returns `None` (with a warning) instead of raising when `git remote` fails, e.g. outside a repository. `reset_remote_cache()` exists for tests. |
| `require_remote()` | Same, for commands that cannot work without a remote: raises `click.ClickException(NO_REMOTE_MESSAGE)`. This is the **single** place that message lives — do not re-raise your own. |
| `ensure_working_path(decline_message=None)` | Get `working_path`, offering to create it when missing (and excluding it from git right away), or failing with a clean `click.ClickException`. Used by `working-env` and by every light-weight pre-flight wrapper. |
| `exclude_from_git(entries)` | Append `(entry, description)` pairs to `.git/info/exclude`. Idempotent; skips with a warning outside a git repository and creates the exclude file when missing. |

**Anything that creates a folder under the repo must exclude it from git in the same step** — that is what
`ensure_working_path` does, and why nothing else should call `os.makedirs(working_path)` directly.

---

## 5. Shell Integration & Deployment

### User Installation Flow

When end-users install `mega_snake` via `uv tool install` or `pipx install`:

1. The package is installed in an isolated virtual environment.
2. The `mgsnake` command becomes available globally.
3. Users add initialization code to their shell profile:
   - **Bash/Zsh**: `. "$(mgsnake shell-path bash)"` → outputs the path to `config_setup.sh`
   - **PowerShell**: `. (mgsnake shell-path pwsh)` → outputs the path to `config_setup.ps1`
4. The initialization script (`config_setup.sh` or `config_setup.ps1`) is sourced, which:
   - Sets `MEGA_SNAKE_SHELL` environment variable
   - Defines `mgsnake_reload` to (re)load the local config file (if present)
   - Calls `mgsnake_reload` once so the local config is applied immediately
**Why this approach?**
- Allows the tool to run anywhere without polluting the user's active Python environment
- Users don't need to manually activate/deactivate virtual environments
- The `mgsnake` console script runs from its isolated `uv tool`/`pipx` environment
- Sourcing the shell setup only configures shell integration (`MEGA_SNAKE_SHELL` and `mgsnake_reload`) per session

### Local Development Setup

**Prerequisites:**
- Python 3.13+
- `uv` package manager

**Setup Steps:**

1. Clone the repository and navigate to the root:
   ```bash
   git clone <repo-url>
   cd unix-scripts
   ```

2. Install dependencies (including dev dependencies):
   ```bash
   uv sync --all-extras
   ```

3. Build the wheel:
   ```bash
   uv build
   ```

4. Install locally for testing:
   ```bash
   uv tool install dist/*.whl --force-reinstall
   ```

5. Add the initialization script to your shell profile (same as end-users do):
   - **Bash/Zsh**: Add `. "$(mgsnake shell-path bash)"` to `~/.bashrc` or `~/.zshrc`
   - **PowerShell**: Add `. (mgsnake shell-path pwsh)` to your PowerShell profile

6. Restart your terminal and verify:
   ```bash
   mgsnake --help
   ```

---

## 6. Development Rules

### 6.1 Code Quality Standards

**ALL code must follow these standards without exception:**

1.  **Type Hinting - MANDATORY for all functions and parameters:**
    -   **All function parameters** must have explicit type annotations (e.g., `name: str`, `count: int`)
    -   **All function return types** must be explicitly declared (e.g., `-> str`, `-> None`, `-> list[str]`)
    -   **Use `Optional[T]`** for optional types instead of `T | None` (e.g., `Optional[str]` not `str | None`)
    -   Example:
        ```python
        def process_data(items: list[str], timeout: Optional[int] = None) -> dict[str, int]:
            """Process items with optional timeout."""
            pass
        ```

2.  **Docstrings - MANDATORY for all modules, classes, and functions:**
    -   **Module-level docstring**: Must be at the top of every `.py` file
    -   **Class docstring**: Required for all class definitions
    -   **Function/method docstring**: Required for every function and method (including `__init__`, `__str__`, etc.)
    -   **Format**: Use the following structure for methods:
        ```python
        """Brief description of what the method does.
        
        Parameters:
            param_name: Description of parameter.
            another_param: Description of another parameter.
            
        Raises:
            ValueError: Description of when this exception is raised.
            RuntimeError: Description of when this exception is raised.

        Returns:
            str: Description of the return value.
        """
        ```
    -   **Note**: If there are no parameters, raises, or returns, explicitly state `None` in those sections.
    -   Example:
        ```python
        def validate_path(path: str) -> bool:
            """Check if the given path is valid and accessible.
            
            Parameters:
                path: The file system path to validate.
                
            Raises:
                ValueError: If path is None or empty string.

            Returns:
                bool: True if the path is valid, False otherwise.
            """
            pass
        ```

3.  **Imports**: Group imports in this order:
    -   Standard Library
    -   Third Party
    -   Local Application
    -   Each group separated by a blank line

4.  **Error Handling**:
    -   Raise `ValueError` for invalid user input
    -   Raise `click.ClickException` for expected CLI errors
    -   Let unexpected errors bubble up to `__main__.py` to be caught by the global handler

5.  **Paths**: Always use `pathlib.Path` or `os.path` joins. Never use string concatenation for paths.

6.  **Language**: All code comments, docstrings, and identifier names (variables, functions, classes, etc.) must be
    written in English, regardless of the language used to discuss the task. This is an English-speaking work
    environment.

7. **Avoid duplicated code**: Each fix, implementation or modification in the codebase must use the existing utilities, helpers, and patterns. Additionally, If you find yourself copying and pasting code, consider refactoring it into a shared utility function or class.

8.  **Consistency**: We must use the same approach and design patterns consistently across the codebase. If a pattern is already established, follow it rather than introducing a new one. If you are writing a new implementation, make sure to check what development patterns are being used in the codebase beforehand, so you can use similar approaches in your new solution unless there is a strong reason to deviate.


### 6.2 Testing & Coverage Requirements (CRITICAL)

**MANDATORY: Any file created, modified, or deleted must have corresponding tests created, updated, or removed respectively.**

#### Core Principles

- **Do not simplify, remove, weaken, or rewrite existing passing tests** unless strictly necessary to fix a defect.
- **Do not exclude files, modules, classes, or functions from the pytest test suite** to artificially increase coverage.
- **Do not modify source code solely to make testing easier** or to reduce the number of required tests.
- **New tests must validate real application behavior**, not be written solely to inflate coverage metrics.
- **Reuse existing fixtures, helpers, and testing patterns** whenever possible to maintain consistency.
- **Preserve the current project structure and testing conventions** throughout all changes.

#### Coverage Requirements

- **Overall project coverage**: Minimum 95%
- **All new or modified source code**: Minimum 98% coverage
- **All tests must pass** before any PR is submitted

#### Testing Workflow

1. **New Source Code**: Create comprehensive tests in `src/tests/{module}/` directory. Ensure 98% coverage.
2. **Modified Source Code**: Update existing tests to reflect changes. Add new tests for new behavior. Maintain 98% coverage.
3. **Deleted Source Code**: Remove or update corresponding tests in `src/tests/{module}/` directory.
4. **Run Tests**: Execute `pytest` to verify all tests pass and coverage goals are met.

```bash
# Run full test suite with coverage reporting
pytest

# This generates:
# - report.html: HTML report of test results
# - coverage_html/index.html: Detailed coverage breakdown by file
# - Fails if coverage < 95% overall or < 98% for new code
```

#### Example: What This Means

**If you modify `config_environment/java_set.py`:**
- Update tests in `src/tests/config_environment/test_java_set.py`
- Add tests for any new functions or branches
- Ensure the modified functions have 98% coverage
- Verify overall project coverage remains ≥ 95%

**If you create `util/new_helper.py`:**
- Create `src/tests/util/test_new_helper.py` with comprehensive tests
- All functions must have 98% coverage
- Tests must validate real behavior, not just code paths

**If you delete a module:**
- Remove its corresponding test file or test class
- Verify overall coverage still meets 95% threshold

### 6.3 Command Documentation Fragments (`resources/docs/`)

Every CLI command has a Markdown fragment at `src/mega_snake/resources/docs/<command-name>.md`, named after the
command's registered name (never after an alias). Fragments are the human-written half of the command reference:
the synopsis, aliases and option list are owned by the Click metadata (`help=`, `short_help=`, `epilog=`, option
`help=`), so a fragment must never duplicate what `--help` already says — it adds the "why", the outputs on disk,
and the caveats.

**MANDATORY maintenance rules — same spirit as the testing rules in §6.2:**

1. **New command** → create its fragment in the same change.
2. **Deleted command** → delete its fragment. **Renamed command** → rename the fragment to match the new name.
3. **Modified command** (behavior, options, arguments, output files, side effects) → re-read its fragment **and**
   its Click metadata, and update whichever no longer matches the code. A logic change is not complete while the
   fragment or the help text still describes the old behavior.

**Fragment format:**
- Body only: no `#` title, no synopsis, no option table.
- Allowed section headings, emitted in this order and each optional: `## Output`, `## Examples`, `## Notes`.
  Write them as `##`; the writer promotes them to `####` so they nest under the `###` command heading
  (see the hierarchy diagram in §3.7). Never hand-write `###`/`####` in a fragment.
- English, like all repo content (§6.1 rule 6).

**What goes in a fragment (follow the shape the existing 17 fragments already use):**

| Part | Content |
|---|---|
| Opening paragraph(s) | The **why**: the problem the command solves, or the design decision behind it ("the zero-config start command", "pipeline via files"). Never a restatement of `help=`. |
| `## Output` | Every file or folder the command writes, with its path, and what each one contains. Required whenever the command touches disk. |
| `## Examples` | Real invocations in a fenced block, when the argument shape is not obvious from the synopsis. |
| `## Notes` | Preconditions (needs a remote, needs `pom.xml`), destructive behavior, locale/platform caveats, and interactions with other commands. |

**Enforcement — four tests in `src/tests/docs_gen/test_docs_gen.py`, parametrized over every command:**

1. `test_every_command_has_a_fragment` — a new command without a fragment turns the suite red, naming the command.
2. `test_no_orphan_fragments` — a renamed/deleted command must not leave a stale `.md` behind.
3. `test_every_documented_command_uses_explicit_help` — compares `cmd.help` against `inspect.getdoc(callback)` so an
   omitted `help=` (which Click silently fills from the docstring) is caught.
4. `test_epilog_never_repeats_generated_content` + `test_fragment_never_repeats_the_epilog` — the no-duplication rule
   above, checked mechanically instead of by convention.

Plus `mgsnake generate-docs --check`, which catches a committed `COMMANDS.md` that no longer matches the code. The
tests and the check catch *different* failures: the tests catch missing/duplicated prose, the check catches a stale
generated file. **After changing any command metadata, run `mgsnake generate-docs` and commit the regenerated
`COMMANDS.md` in the same change.**
