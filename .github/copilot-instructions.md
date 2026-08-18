# GitHub Copilot Instructions for `mega-snake`

## 1. Project Overview & Philosophy

`mega_snake` is a robust Python CLI tool designed to standardize the local development lifecycle. It acts as a "Swiss Army Knife" for developers, primarily automating the complex configuration of VS Code environments for Java/Gradle, but extending into Git workflows, release orchestration, dependency auditing and shell integration.

> ### ⚠️ THE FIRST RULE: `mgsnake` IS A PRODUCT FOR ITS USERS, NOT A SCRIPT FOR ITS AUTHOR
>
> **Every command is built for the developers who install `mega-snake`, never for this repository's own
> convenience.** A command must never be shaped, restricted, or special-cased to fit how _this_ project
> happens to work.
>
> The reasoning is decisive: if the goal were to automate the maintainer's own workflow, `mgsnake` would be
> massive overkill — a handful of shell scripts symlinked into `/usr/bin` would do the job. The entire cost
> of this project (a packaged CLI, a published distribution, generated documentation, 95%+ coverage) is
> justified **only** because the output is a tool for the world.
>
> **What this forbids, concretely:**
>
> - Reading this repository's `pyproject.toml`, `CHANGELOG.md`, or CI configuration from a user-facing
>   command. A user's project has none of those, or has different ones.
> - Assuming a Python/uv project. Most users of `working-env` and `set-java` are on Java/Gradle.
> - Encoding this repository's conventions (branch names, tag shapes, release cadence) as command defaults.
> - "Fixing" a user-facing command so that it fits a workflow of this repo. When the two conflict, **the
>   repo's workflow bends, not the command.**
>
> **When a genuine need for repo-only tooling arises**, it does not become a user-facing command. Ask "would
> a stranger installing `mega-snake` want this?" — if the answer is no, it does not belong in a user-facing
> command group.
>
> #### ⚠️ Known violation — do not treat the current layout as the example to follow
>
> **`generate-docs` and `man` (§3.7) break this rule today.** They introspect **`mgsnake`'s own CLI**
> (`from mega_snake.__main__ import cli`), so a user running `mgsnake generate-docs` in their project gets
> a `COMMANDS.md` describing _mgsnake_, not their tool. This is **accepted technical debt, not a
> precedent**; the agreed direction is to move every mega-snake-only command into a dedicated module.
> Until that lands: do not add new repo-only commands to user-facing groups, do not cite `generate-docs`
> as justification for doing so, do not "fix" a user-facing command by making it repo-aware, and keep
> `docs_gen` self-contained so the eventual move stays mechanical.
>
> Everything outside `docs_gen` honours the rule: `dependency_audit` reads the _user's_ lockfiles through
> ecosystem auto-detection, and `create-release` derives tags from the _user's_ GitHub releases — neither
> reads this repository's `pyproject.toml` or `CHANGELOG.md`.

**Core Philosophy:**

- **Zero Config Start**: A developer should be able to run `mgsnake working-env` and have a fully functional IDE state immediately.
- **Idempotency**: Commands should be safe to run multiple times without destructive side effects unless explicitly requested.
- **System Integration**: The tool deeply integrates with the OS shell (Bash/Zsh/PowerShell) and external tools (Git, Java, Gradle).

**Tech Stack:**

- **Runtime**: Python 3.12–3.13 (`requires-python = ">=3.12,<3.14"`). Development happens on 3.13
  (`.python-version`), while mypy is pinned to 3.12 on purpose, so type checking catches what would break on the
  oldest interpreter we claim to support.
- **CLI Framework**: `click` (Command composition), `rich-click` (Beautiful help text/formatting)
- **UI/Output**: `colorama` (Terminal colors), `rich` (Tables/Trees)
- **Dependency Management**: `uv`
- **Shell Interop**: Custom shell scripts (`config_setup.sh/ps1`) that wrap the python execution.

---

## 2. Architecture & Patterns

### 2.1 Entry Point & CLI Orchestration (`src/mega_snake/__main__.py`)

The application uses a `click.Group` with a custom `CliGroup` class to support command aliases. The entry point `cli()` function initializes global application properties before any command runs.

**Critical Pattern: Initialization flags (`no_init` and `skip`)**
Before invoking a subcommand, `cli()` reads the metadata attached by `@cli_metadata(...)` and decides _how much_
initialization to run. There are exactly **three** initialization levels, driven by two flags:

| Flag      | Level            | `init_app_properties`                                                  | Use it when                                                                                                        |
| --------- | ---------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| _(none)_  | **Full**         | Called; `working_path` must exist or the command fails                 | The command needs a valid workspace (`set-java`, `set-gradle`, …)                                                  |
| `skip`    | **Light-weight** | Called with `light_weight=True`; a missing `working_path` is tolerated | The command can run anywhere, but still wants properties/logging when available (`create-release`, `diff-tree`, …) |
| `no_init` | **None**         | **Never called** — `cli()` returns early                               | The command must work _before_ the environment exists at all (`shell-path`)                                        |

```python
# src/mega_snake/__main__.py
@click.pass_context
def cli(ctx: click.Context, log_level: str) -> None:
    # ...
    metadata = getattr(cmd.callback, ATTR_METADATA, {})   # ATTR_METADATA == "_cli_metadata"
    flags: Optional[set[str]] = metadata.get(META_FLAGS)  # META_FLAGS    == "flags"
    if flags and "no_init" in flags:
        return                      # No AppProperties at all, and no MEGA_SNAKE_SHELL check
    ws_advice(f"Invoking subcommand: {cmd_name}")
    if flags and "skip" in flags:
        light_weight = True         # AppProperties built, working_path validation deferred
    # ...
    init_app_properties(log_level, shell, light_weight)
```

**Note the nesting**: `cli_metadata(**metadata)` stores its kwargs under the callback's `ATTR_METADATA` attribute
(`_cli_metadata`), so `@cli_metadata(flags={"skip"})` produces
`getattr(callback, ATTR_METADATA) == {"flags": {"skip"}}`. That is why the entry point reads `metadata.get("flags")`
and not `metadata` directly — `metadata` is the whole kwargs dict, `"flags"` is just one of its keys (`META_FLAGS`).
`wrapper_decorator.update_flags` propagates these from both the module wrapper _and_ the command callback onto the
wrapping command, which is what makes a module-level `@cli_metadata(flags={"skip"})` apply to every command in the
module.

**When `no_init` is the only option**
`no_init` exists for the **bootstrap problem**, not as a "lighter light-weight". Full and light-weight initialization
both require `MEGA_SNAKE_SHELL`, and `cli()` raises `EnvironmentError` when it is unset. But that variable is exported
by `config_setup.sh`, and the user's shell profile has to run `mgsnake shell-path bash` _to find that script in the
first place_ — so at that moment the variable does not exist yet. Returning early is the only way `shell-path` can
answer. Consequences for any `no_init` command:

- `AppProperties` is never constructed: `get_property()`, `working_path`, `log_file` and the `.code-workspace` are all
  unavailable. Depend only on `importlib.resources` and the arguments.
- Nothing is logged to file, and the `ws_*` helpers are pointless — `shell-path` deliberately uses `click.echo` because
  its stdout is consumed by command substitution (`. "$(mgsnake shell-path bash)"`) and must stay clean.

**Keep `no_init` stdout clean.** Anything a shell captures with `$(...)` must print _only_ the value. `ws_advice` is
level-gated (it checks `logger.level`), so it is silent when logging was never configured — but that is a property of
the current initialization order, not a guarantee. Never add unconditional `ws_*` output to a command whose stdout is
consumed by a script.

**What light-weight mode (`skip`) actually defers**
When `working_path` (e.g. `workspace_temp`) is missing, `AppProperties.__init__` raises `FileNotFoundError` _after_ setting
`resources_path`, `working_path`, `local_config_file`, `local_env_file`, `shell` and a best-effort `workspace_file`.
`init_app_properties` swallows that error when `light_weight=True`, which leaves **unset**: the `_log_level` attribute,
`log_file`, `graphql_schema_file` and the `__post_init__` validation — and skips `formatting.config_log`, so nothing is
written to the log file and `--log-level DEBUG` has no effect (`ws_advice` checks `logger.level`).

Console output is unaffected: every `ws_*` helper in `formatting.py` calls `print()` **before** `logger.*`, so the tool
always talks to the user regardless of whether logging is configured. That is the decoupling light-weight mode relies on.

**Completing a deferred initialization (`complete_app_properties`)**
Commands that are light-weight but _do_ need the working path (see the pre-flight wrappers below) call
`complete_app_properties()` right after securing the folder. It finishes exactly where `__init__` stopped
(`_log_level`, `log_file`, `graphql_schema_file`, `config_log`) and is idempotent, so it is a no-op after a full
initialization. `_check_forbidden_execution` treats `complete_initialization` as part of the initialization
(`INITIALIZATION_METHODS`), which is what allows the init-only validators to run from there.

**Rule of thumb:** a command may be light-weight _and_ depend on `working_path` only if its wrapper offers to create the
folder and fails with a clean `UserDeclinedError` when the user declines. Never let it reach the command body without it.

### 2.2 Command Registration & Aliases (`src/mega_snake/util/cli_group.py`)

Click has no alias support of its own, so `CliGroup` provides it: one command reachable under several names.

**Usage** — a module registers its own commands and aliases on its group; `__main__.py` then re-registers each of
those commands on the root group, wrapped with the module's pre-flight check (§2.3):

```python
# src/mega_snake/diff_tree/module.py
# Registers 'diff-tree', reachable as 'dt' and 'tree'
main.add_command_with_alias(diff_tree, ["dt", "tree"])
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

**Names and aliases are unique, and the CLI refuses to start otherwise.** Click's registry is a plain dict, so a
second registration under an existing name _replaces_ the first one: the shadowed command becomes unreachable while
its own unit tests keep passing, because they exercise the command object directly and never go through the registry.
That failure mode has shipped before — a duplicated command with 100% coverage on code that could never run.
`CliGroup.add_command` and the alias registration therefore both call `__reject_duplicate`, which raises
`click.UsageError` naming the two colliding origins:

```text
Command 'scan-dependencies' is already registered by 'Dependency Audit' and cannot be reused by 'Light Weight'.
```

Registration happens at import time, so a collision fails the whole suite immediately rather than at first use. The
check is anchored on the **resolved** name (`name or cmd.name`), so an explicit `add_command(cmd, name)` override is
covered too, and synthetic alias commands inherit their owner's `ATTR_GROUP` precisely so this message points at the
owning command instead of at `cli_group`'s own module.

**Attribute constants.** `cli_group.py` owns the names of every custom attribute the CLI hangs on commands and
callbacks. Import them instead of writing the string literal:

| Constant        | Value             | Meaning                                                                                                                                                                                |
| --------------- | ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ATTR_METADATA`    | `"_cli_metadata"`        | Attribute where `@cli_metadata` stores **all** its kwargs.                                                                                                                             |
| `META_FLAGS`       | `"flags"`                | Metadata **key** holding the initialization flags (`skip` / `no_init`), inside the dict stored under `ATTR_METADATA`. Deliberately a different string from `ATTR_METADATA` — see §2.1. |
| `META_RELOADS_ENV` | `"reloads_environment"`  | Metadata **key** marking a command that rewrites a local environment file, so the shell must re-source it (§7.4).                                                                       |
| `ATTR_ALIAS`       | `"aliases"`              | The alias list, read by rich-click and by the docs iterator.                                                                                                                           |
| `ATTR_DOCS`        | `"docs_fragment"`        | Overrides the fragment filename (defaults to the command name).                                                                                                                        |
| `ATTR_GROUP`       | `"docs_group"`           | Overrides the documentation group title (see §3.7).                                                                                                                                    |

`CliGroup.add_command` resolves `ATTR_DOCS`/`ATTR_GROUP` onto the command at registration time, so every command has
them by the time anything iterates the registry.

**Group title resolution is decided by provenance, never by the shape of the string.** An explicit title (set via
`@cli_metadata(docs_group=...)` or already present on the command) is used **verbatim**; only a title _derived_ from
the module path is reformatted with `.title()`, because there the raw value is an identifier like `remote_branches`.
Do not reintroduce heuristics such as "if it contains a space it must already be a title" — `docs_group="GraphQL"`
would silently become `"Graphql"`.

### 2.3 The Wrapper Pattern (`module.py` files)

Each functional module (e.g., `config_environment`) exposes an `add_wrapper` decorator. This allows module-specific checks to run before the command execution, keeping the core logic clean.

**Example from `src/mega_snake/diff_tree/module.py`:**

```python
@cli_metadata(flags={"skip"})
def wrapper(_ctx: click.Context, *_args, **_kwargs) -> None:
    # Pre-flight check: secure the scratch folder, then finish the deferred initialization
    ensure_working_path()
    complete_app_properties()

add_wrapper = wrapper_decorator(wrapper)
```

Every module exports exactly that pair — its command group as `main`, and `add_wrapper` — and `__main__.py` walks
its `MODULES` list to register each command wrapped with its own module's checks:

```python
# src/mega_snake/__main__.py
for group, add_wrapper in MODULES:
    for command in group.commands.values():
        cli.add_command(add_wrapper(command))
```

**Educational Logic:**
This implements the **Decorator Pattern**. Instead of repeating validation logic in every command, we define it once in the wrapper. The `__main__.py` entry point applies this wrapper dynamically when registering commands, ensuring checks only run when a relevant command is invoked. The wrapper is also where a module's `@cli_metadata` flags are declared once for all of its commands, and registration order in `MODULES` drives the order shown in the help output.

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

**A `click.Group` keeps being a group.** The same rebuild would otherwise drop `commands`, since
`click.Command.__init__` knows nothing about it, and a nested group registered through a module wrapper would come
out as a leaf command with no subcommands — `mgsnake config get` would simply stop resolving, with nothing to see
until someone ran it. `_rebuild_command` therefore instantiates `type(command)` and adds `commands` for groups.
`test_wrapper_decorator_keeps_a_group_a_group` pins it.

**Per-command initialization flags win over the module wrapper's.** `update_flags` merges the wrapper's metadata
first and the command callback's second, so a module whose commands need different levels (see `jira_api`, §3.9)
declares no `flags` on its wrapper and lets each command carry its own `@cli_metadata(flags={...})`. Aliases go
through the same path, because they are built from the same callback.

---

## 3. Core Functional Modules

### 3.1 Environment Configuration (`src/mega_snake/config_environment/`)

This is the most complex module, responsible for generating `.code-workspace` files. It configures the "settings" section of the workspace file directly, avoiding reliance on `.vscode/settings.json`.

#### `working-env`

- **Logic**:
  1. Validates Git repository status, offering to continue without it rather than failing.
  2. Secures the working path, and excludes it from Git when there is a repository.
  3. Resolves the **active stacks** — from `--stack`, or by detecting marker files in the current
     directory (`models/project_stack.py`, below).
  4. Loads local developer overrides (`initial_load`).
  5. Configures the tools of the active stacks only: `set-java`, `set-gradle` and `set-maven` each
     run when their stack is active, and are reported as skipped otherwise.
  6. Generates the VS Code tasks, launch configurations, log watchers and extension
     recommendations **belonging to the active stacks**.

#### `models/project_stack.py` — the stack model

**Every artifact `working-env` emits is tagged with the stack that owns it, and the workspace
writer keeps only the artifacts of the active stacks.** That single rule replaced the scattered
`os.path.exists` checks the module used to grow, and is why the Java-centric default is gone: a
repository with no JVM build file is never asked for a JDK.

`ProjectStack` is the single source of truth. Each member carries its marker files, the stacks it
implies, the extensions and the `files.associations` entries it contributes:

| Helper | Role |
| --- | --- |
| `detect_stacks(root)` | The active stacks, from the marker files in **one** directory — never recursive, so a vendored `package.json` cannot activate Node. |
| `resolve_stacks(selected, root)` | `--stack` wins outright and skips detection entirely; `all` means every stack a user may ask for. |
| `expand(stack)` | A stack plus everything it implies, **transitively** — depth lives here alone, so a new stack implying `gradle` still brings `java`. |
| `filter_by_stack(members, stacks)` | The one filter every artifact enum goes through. |
| `sort_stacks(stacks)` | Deterministic ordering; stacks travel as sets, and set iteration is not stable. |
| `StackAware` | The protocol (`stack: ProjectStack`) that `VscodeTask`, `VscodeLaunch`, `VscodeInput` and `LogWatcher` all satisfy. |

Three things that are easy to get wrong when adding a stack or an artifact:

- **`COMMON` is always active** and is what an untagged artifact defaults to. Tag deliberately:
  an artifact left on `COMMON` lands in every workspace, on every repository.
- **An `opt_in` stack is absent from `--stack` and from `all`**, so its marker file is the *only*
  way in. `SNAKE` uses this to keep mega-snake's own debug launch out of every user's Python
  repository — §1 FIRST RULE, in enum form.
- **The tagging is a graph, not a set of labels.** A task redirects into a `LogWatcher`, depends on
  other tasks by label, and calls a `VscodeInput` through `${input:<id>}`. Tagging a member with a
  stack that does not activate its referent writes a dangling reference into the workspace, and VS
  Code only reports it when the developer runs the entry. `src/tests/config_environment/models/test_stack_references.py`
  walks that whole graph as an invariant — keep new references inside it rather than adding a
  per-member example test.

**Nothing already in the `.code-workspace` is ever removed.** Narrowing the stacks adds less; it
never takes anything away, which is what makes the change safe to roll out on existing workspaces.

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

`set-maven` (`maven_set.py`) follows the same shape for Maven: it resolves the installation from the shell or from
`--maven-home`, and writes `M2_HOME` plus the executable path into the same settings structure.

**Technical Note: JSON with Comments**
Every command that touches the `.code-workspace` file has to cope with the comments it contains, which the standard python `json` library rejects. We use a custom `load_json_with_comments` utility to handle VS Code's configuration format safely without stripping those comments, which are vital for developers understanding the config.

#### `init-local-config` (`local_config.py`)

Creates a local developer-specific configuration file that is **ignored by Git**.

**Why?**
Developers often have machine-specific tokens, paths, or aliases that shouldn't be committed to the repo. `init-local-config` generates a shell-specific file (`.sh` or `.ps1` logic embedded) that is sourced by the main environment. This pattern allows the tool to support "Convention over Configuration" while still allowing for "Configuration" when necessary.

### 3.2 Git Utilities (`src/mega_snake/diff_tree/`)

#### `diff-tree` (`dt`)

Generates a visual tree representation of changed files.

**Module layout** — the shape every module follows: `diff_tree/diff_tree.py` holds the command and its helpers,
`diff_tree/module.py` holds the `CliGroup`, the pre-flight `wrapper` (carrying the `skip` flag) and `add_wrapper`
(§2.3).

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
- Each raw line is categorized with `FileType.from_symbol(symbol)` (the `M`/`A`/`D` letter in the fifth field), the
  paths are replayed into a throwaway tree under `workspace_temp/diff_tree/diff_tree_dummy_repo`, and the
  `directory_tree` library renders that tree as text.
- The output directory is wiped (`shutil.rmtree`) and recreated (`os.makedirs`) on **every** run, so no file write
  depends on a directory left behind by a previous run.
- No remote is required: `get_main_branch` falls back to the current local branch, so its wrapper only calls
  `ensure_working_path()` + `complete_app_properties()`.

### 3.3 Remote Branch Management (`src/mega_snake/remote_branches/`)

#### `remote-branches-details`

Analyzes remote branches to suggest cleanup candidates, filtered by merge status with `-f` (`M`/`U`/`A`).

**Merge detection (`RemoteBranch.from_branch`)** — a branch counts as merged when _any_ of these holds, checked in
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
`Repo.require_remote()` → `ensure_working_path()` → `complete_app_properties()`. The commands themselves still call
`Repo.require_remote()`; because the resolution is memoized on the class, that costs no extra `git remote` and no
second prompt.

### 3.4 Release Management (`src/mega_snake/light_weight/create_release.py`)

Automates GitHub releases, creating tags and proper GitHub Release entries.

**The one positional argument that decides everything is `release_type`:**

- `p`: Prerelease (`--prerelease`)
- `l`: Latest (`--latest`) — asks for confirmation before creating a new latest release
- `r`: Regular release (`--latest=false`) — publishes **without** taking the `latest` mark; if GitHub moves the
  `latest` pointer anyway, the command restores it to the previous latest release

The three types are explained in prose in `resources/docs/create-release.md` (by their _effect_ — which version
users land on — not as a flag list, since the synopsis already shows `{p|r|l}`). The `epilog=` documents only the
positional arguments, per §3.7.

**Logic:**
The new tag is **derived, never typed**: the command reads the latest GitHub release, increments the component
named by `--version-part` (`patch` by default, resetting everything to its right), renders it through the tag
pattern, and hands the result to the `gh` CLI. `--tag-suffix` only adds a pre-release label, and is refused for the
`l` type because GitHub grants the `latest` pointer only to a plain version.

Deriving the tag from the published release — rather than from a local tag or a hand-typed value — is what keeps the
sequence continuous when two people cut releases from different checkouts.

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
Instead of re-implementing the GitHub API client (which requires managing OAuth tokens, permissions, etc.), we delegate the heavy lifting to the `gh` binary. This is a common "shell wrapper" pattern where Python manages the _control flow_ and _validation_, but the shell executes the _remote action_.

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

- **`graphql-schema`** (`graphql_schema.py`) — compiles a directory of `.graphql` files into one schema **and** an
  introspection JSON, because frontend tooling (Apollo, IDE plugins) needs the full introspection result for
  autocompletion and type checking, not just the SDL.
- **`expired-certs-jks`** (`jks_expired_certs.py`) — audits a Java KeyStore through `keytool`. The hard part is
  parsing `keytool -v -list`, whose date format follows the system locale: treat locale variation as expected input
  here, not as an edge case.
- **`msg`** (`echo.py`) — exposes the `ws_*` helpers to the shell, so `config_setup.sh` prints status through the
  same formatting as the CLI instead of raw `echo`.

### 3.7 Command Reference Generation (`src/mega_snake/docs_gen/`)

#### `generate-docs`

Generates `COMMANDS.md` — the full command reference — by introspecting the live Click objects and appending the
hand-written fragments from `resources/docs/` (§6.3).

**The governing principle:** every fact lives in exactly one place. Whatever the program already knows (synopsis,
options, types, defaults, aliases, grouping) is **generated** and cannot drift. Whatever only a human knows (why the
command exists, what it writes to disk, the caveats) is **hand-written** in a fragment. Neither half may restate the
other, and two tests enforce it (§6.3).

**Module layout** (same shape as every other module):

| File                          | Responsibility                                                                                                            |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `docs_gen/introspect.py`      | Walks the CLI and normalizes it into `IntrospectedCommand` dataclasses. Owns `normalize_help()` and `normalize_epilog()`. |
| `docs_gen/markdown_writer.py` | Pure rendering: dataclasses → Markdown. Owns the table-escaping helpers and `write_or_check_document()`.                  |
| `docs_gen/generate_docs.py`   | The `generate-docs` Click command only.                                                                                   |
| `docs_gen/man_page.py`        | The `man` Click command: alias resolution, terminal rendering, paging.                                                    |
| `docs_gen/module.py`          | The `CliGroup`, the `wrapper` (carrying `docs_group="Documentation"`) and `add_wrapper`.                                  |

`generate-docs` is `@cli_metadata(flags={"no_init"})`: it needs no workspace, no git and no `MEGA_SNAKE_SHELL`, so it
resolves the packaged fragments through `importlib.resources` and must never call `get_property()`. It imports the
root `cli` **lazily inside the function**, because `__main__` imports this module to register the command.

**Flags:** `--output PATH` (default `COMMANDS.md`) and `--check` (render in memory, diff, exit non-zero when stale).
`--check` compares with `splitlines()` and writes with `newline="\n"`, so CRLF/LF differences never cause a false
failure on Windows.

#### `man`

Pages the same reference in the terminal — the whole document, or one command when `mgsnake man [COMMAND]` names one.
Also `no_init`, and it imports the root `cli` lazily for the same reason.

**It renders in memory; it never reads `COMMANDS.md`.** That file is committed to the repository but is _not_ shipped
in the wheel (`packages = ["src/mega_snake"]` only sweeps in the package tree, and `COMMANDS.md` sits at the repo
root). Reading it would produce a command that works in a source checkout and fails for every installed user — the
exact class of bug that never shows up in development. The fragments _are_ packaged, so introspection plus
`importlib.resources` is the only source that exists in both environments.

**Nothing is installed to `/usr/share/man`.** `uv tool install` and `pipx` create an isolated environment and copy
nothing to the system man path, so `man mgsnake` cannot resolve. Paging from inside the CLI is also the only form
that works on PowerShell, where `man` does not exist.

Four details that are easy to get wrong when touching this command:

- **Paging is wrapped in a fallback, and the fallback is load-bearing.** `click.echo_via_pager` raises `TypeError` on
  the interactive Windows path of click 8.4.x: `_pager_contextmanager` picks `_tempfilepager`, which yields a binary
  `NamedTemporaryFile`, and `get_pager_file` only wraps a stream exposing a `.buffer`, so `str` reaches a binary
  handle. No click release fixes it and pinning backwards drops below what rich-click resolves, so `_page_or_echo`
  catches `TypeError`/`UnicodeEncodeError` and prints plainly instead. **Catch only those two** — widening it hides
  real failures, and a test pins that. Do not "cover" this with a `# pragma`: the regression test forces click's
  Windows context manager on any platform, which is the only honest way to exercise it. Re-check it whenever the
  click pin in `pyproject.toml` moves.
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

| Level  | What lives there                                  | Written by                                   |
| ------ | ------------------------------------------------- | -------------------------------------------- |
| `#`    | Document title (`# Available Commands`)           | The writer (`GROUP_HEADING`)                 |
| `##`   | Documentation group                               | The writer, from `docs_group`                |
| `###`  | Command name                                      | The writer, from the registered command name |
| `####` | Fragment sections (`Output`, `Examples`, `Notes`) | **You**, as `##` in the fragment file        |

So: **never write `###` or `####` in a fragment to start a section.** Write `##` and let
`_render_fragment()` shift it down. Getting this wrong makes a fragment section outrank the command it documents,
which silently breaks the document outline (and any tooling that builds a table of contents from it). Two tests
pin it: `test_generate_docs_renders_fragment_sections_below_the_command_heading` and
`test_fragment_sections_never_outrank_their_command`.

#### The fields the generator consumes — and what belongs in each

This is the contract every command must satisfy. **When adding or changing a command, walk this table top to bottom.**

| #   | Source                    | Rendered as                                                           | What to put there                                                                                                                                                                                                                                              |
| --- | ------------------------- | --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `short_help=`             | _(not in `COMMANDS.md`)_ — the description column of `mgsnake --help` | One line, under ~60 chars, verb-first ("Creates a new release on GitHub…"). It is what a user scanning the command list reads.                                                                                                                                 |
| 2   | `help=`                   | The paragraph under the command heading                               | **Mandatory and explicit.** One or two sentences saying what the command does and, when it is not obvious, _how_. Never omit it: Click would fall back to the callback docstring and publish a "Parameters: …" block into the reference. A test enforces this. |
| 3   | _(derived)_               | `**Synopsis:** mgsnake <cmd> [OPTIONS] ARGS`                          | Nothing to write — generated from `Command.get_usage()`. Never restate it by hand.                                                                                                                                                                             |
| 4   | `aliases`                 | `**Aliases:** ...`                                                    | Set through `add_command_with_alias`. Prefer short, memorable aliases; they are the daily-use form.                                                                                                                                                            |
| 5   | option `help=`            | The options table                                                     | **The single source of truth for every flag.** Put the _full_ explanation here, including allowed values and what each one means. This is the field to enrich when a flag is hard to understand — not the epilog.                                              |
| 6   | `show_default=True`       | `[default: x]` in the table                                           | Use it whenever a default is meaningful to the reader (e.g. `--password` defaulting to `changeit`). Cheaper and drift-proof compared to writing the default into the help text.                                                                                |
| 7   | `epilog=`                 | A bullet list / paragraph after the table                             | **Positional arguments only** (Click never tabulates them) plus anything genuinely extra. See the rules below.                                                                                                                                                 |
| 8   | `resources/docs/<cmd>.md` | The prose after everything else                                       | The "why", outputs on disk, examples and caveats (§6.3).                                                                                                                                                                                                       |
| 9   | `docs_group`              | The `##` section grouping commands                                    | Optional; defaults to the module name titled. Set it when the module name is not a good public title.                                                                                                                                                          |

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
usage: mgsnake create-release <release_type> [notes] [branch]\n
Args:\n
    release_type: char - 'p' (prerelease) | 'l' (latest) | 'r' (regular release)\n
    branch: Optional[str] - branch to create the release from. Default is the current branch.
"""
```

→ renders as `- \`branch\` — branch to create the release from. Default is the current branch.`

**Never move detail out of an option `help=` into an epilog.** If a flag needs a long explanation, the explanation
belongs in field #5, where both `--help` and `COMMANDS.md` show it. An epilog that documents a flag is dropped, so
that detail would be lost from the reference entirely.

#### Text normalization (why the output is clean Markdown)

Click/rich help strings carry `\b` markers, manual `\n` wrapping and leading indentation. Two normalizers handle it:

- `normalize_help()` — strips `\b`, dedents, and collapses each paragraph's manual line breaks into one line while
  keeping blank-line paragraph separation.
- Table cells get extra treatment, because a Markdown table row **ends at the first newline** and is split on `|`
  _before_ any inline parsing:
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

### 3.8 Persistent State (`src/mega_snake/state/`)

The `config` command group (`get` / `set` / `unset` / `list` / `export`) is the user-facing half of
`util/store.py` (§4.4). Two details about how it is wired:

- **It is a `click.Group` nested inside the module's `CliGroup`**, so it is one entry in `COMMANDS.md` with one
  fragment. The generator does not introspect subcommands, so `resources/docs/config.md` is where they are
  documented — that is the "what only a human knows" half of §6.3, not an accident.
- **The whole group is `no_init`, not `no_init` + `skip` per subcommand.** A group carries a single set of
  initialization flags for everything under it, and `config get` / `config export` must answer before the
  environment exists (they are read with `$(...)` and `eval`). That costs nothing because the store is
  deliberately independent of `AppProperties`. Consequence: **only `click.echo` may write in `get` and
  `export`**, and only the value. The `ws_*` helpers are safe next to them nowadays (they all write to stderr,
  §4.1) and `list` uses `ws_info` for its empty case, but the payload of these two is the whole of their stdout.
- **`config export` defaults to `--scope global`, and that is a correctness decision, not a preference.** It is
  documented as something to `eval` from a shell profile, which runs in whatever directory the terminal opened
  in. An exported variable is the *top* layer of the precedence chain, so exporting the `repo` scope from there
  pins one clone's `jira.project_key`/`jira.board_id` onto the whole session and every other clone then resolves
  them from the environment — `jira-issues` in repo B downloading repo A's board, exit 0, no warning.

### 3.9 Jira Integration (`src/mega_snake/jira_api/`)

Replaces four Bash scripts (`get_auth_header.sh`, `getJiraBoard.sh`, `getSprintInfo.sh`,
`jira_board_issues.sh`) that depended on `bash`, `jq`, process substitution and `base64 -w 0` (a GNU-only flag
that fails on macOS). Layout: `auth.py` (Authorization header), `client.py` (`JiraClient`), `models.py`
(`JiraConfig`, `Board`, `Sprint`), `board.py` / `sprint.py` / `issues.py` (one command each), `projection.py`
(the raw-issue → compact-schema mapping plus `FieldIds`), `module.py`.

**`requests` is imported lazily, inside `_build_session`.** ~100 ms against ~28 ms for `urllib.request` — noise
next to a Jira round trip, but pure loss for the other 19 commands, which never make one. `docs_gen` already uses
this pattern for the root `cli`. `test_requests_is_not_imported_at_module_import_time` imports the CLI in a clean
subprocess and asserts `requests` is absent from `sys.modules`; **never hoist that import to module level.**

**Retry and pooling are delegated to `urllib3.util.Retry` and `requests.Session`, on purpose.** Backoff,
honouring `Retry-After`, and deciding which statuses to replay is exactly the kind of hand-written code that
produced the defects this module replaces, and every branch of it would need its own test to clear the 98% bar.
Only `GET` is retried; 401/403/404 are deliberately **not** in `RETRY_STATUS`, because a bad token does not
become valid on the second attempt. Tests assert the *policy mounted on the adapter*, not the mechanics —
retrying for real would be testing urllib3.

**Failures are decided by the HTTP status, never by the shape of the body.** The shell version asked `jq` whether
the response looked like an error object, so a 401 with an empty body sailed through as success. Every handled
status has one message in `STATUS_MESSAGES`, which the tests compare by equality.

**Settings resolve through the store (§4.4); credentials never do.** `jira.domain` and `jira.email` come from
`env var > repo > global`; `JIRA_API_TOKEN` is read from the environment only (`JIRA_MCP_TOKEN` still works as a
deprecated fallback and warns **on stderr**). `jira.board_id`, `jira.field.story_points` and `jira.field.sprint`
are caches written by the commands themselves — the board cache is only trusted when the resolved project key
matches the stored one, so an explicit key can never be answered with another project's board.

**The two endpoint families page differently, and mixing them up is silent.** `/rest/api/2/search/jql` sends
`nextPageToken` and omits it on the last page → `paginate_tokens`. The whole Agile API (`/rest/agile/1.0/*`)
pages with `startAt`/`maxResults` and closes the walk with `isLast` or `total`, and **never** sends a token →
`paginate_start_at`. Reading an Agile path with the token paginator reads page one, finds no token, and returns:
the caller gets a truncated result with exit code 0, which in `jira-issues` means every sprint issue past the
first page is written out as `activeSprint: false`. `paginate_start_at` advances the offset by how many items
*came back*, never by the requested page size, because Jira caps `maxResults` server side — which is also why a
short page cannot be used as the end signal. The doubles in `jira_doubles.py` (`sprint_listing_page`,
`sprint_issues_page`) exist so a test cannot accidentally pin a shape Jira does not produce; that is exactly how
this defect once passed review with a green test.

**Custom field ids are resolved by name.** `customfield_10016`/`customfield_10020` are per-instance, so the
hardcoded ids silently projected `null` on any other tenant. They survive only as a last-resort fallback, with a
warning — and **a fallback is never cached.** Storing one would make the next run take the cache branch, skip
the field endpoint and use the wrong id *without warning*, with no flag to undo it: the same defect, relocated
inside the cache. Only a real match is written to the store, one field at a time.

**`_pick` must keep `jq`'s null semantics.** `null | {id, key}` yields `{"id": null, "key": null}`, not `null`.
The documented recipes find orphan stories with `.fields.parent.key == null`, which throws the moment `parent`
itself becomes null. A test pins it with the negative assertion.

**This module mixes initialization levels, so its `wrapper` is empty and carries only `docs_group`.**
`jira-board`/`jira-sprint` are `no_init` (machine-readable stdout) and `jira-issues` is `skip` (writes to
`working_path`). A module wrapper runs for *every* command in the module, so the pre-flight that `jira-issues`
needs — `ensure_working_path()` + `complete_app_properties()` — lives in its own command body instead. Per-command
flags win because `wrapper_decorator.update_flags` merges the module wrapper first and the callback second.
That pre-flight is also **conditional on `--output` being absent**: with an explicit destination the run never
touches the working path, so prompting to create `workspace_temp` (and exiting 114 when the user declines) would
be a question about a folder it will not write to.

**Rule for the `no_init` commands:** `click.echo` with the JSON, and nothing else, ever. Errors are
`click.ClickException`, which Click writes to stderr with exit code 1. Warnings use the ordinary `ws_*` helpers,
which write to stderr (§4.1) — this module briefly carried its own `click.echo(..., err=True)` wrapper from back
when they printed to stdout; do not reintroduce one.

---

## 4. Utilities & Helpers

### 4.1 Output Formatting (`src/mega_snake/util/formatting.py`)

** STRICT RULE**: NEVER use `print()`. Always use valid logging/formatting functions.

- `ws_info(msg)`: ℹ️ Blue info message.
- `ws_success(msg)`: ✅ Green success message.
- `ws_warning(msg)`: ⚠️ Yellow warning.
- `ws_error(msg)`: ❌ Red error.
- `ws_advice(msg)`: 💡 Helpful tip/advice.
- `ws_tip(dict)`: 🎨 Multi-colour tip.

#### ⚠️ Every `ws_*` helper writes to **stderr**. stdout belongs to the command's output.

stdout carries what a command _produces_ — the value a caller consumes. Progress, status and
diagnostics are not that, and POSIX puts them on stderr precisely so the two can be separated:
`mgsnake cmd 2>/dev/null` keeps the payload, and `$(mgsnake cmd)` captures the payload alone. Neither
works while a status line shares the stream with the result.

The split has to be **uniform across the whole family**: one helper that still prints to stdout is
enough to corrupt a captured value, and the corruption shows up at a distance, only for the commands
and log levels that happen to reach it. Uniformity is what lets a command emit a value on stdout
without auditing every helper it might call.

**Writing to stdout is therefore a deliberate act**, and only `click.echo` does it, in the few
commands whose output is consumed by a script (`shell-path`, `local-config-path`, `local-env-path`). The user sees
no difference: a terminal shows both streams. `test_every_ws_helper_writes_to_stderr_only` walks the
whole family and fails naming any helper that regresses.

### 4.2 Property Management (`src/mega_snake/util/props.py`)

#### ⚠️ CRITICAL: `config.properties` is a packaged distribution file, not a user setting file

`src/mega_snake/config.properties` **ships inside the wheel** and is read on every full or light-weight
initialization, on every machine. It holds the distribution's own resource names — `working_path`,
`local_env_file_name`, `resources_path` and friends — the things the package needs to find itself. `_check_property`
therefore treats a missing key as `InternalStateError`: a packaging defect, never something the user can supply.

**What follows from that, and it is the whole point of this note:** a user cannot edit it (it lives inside an
isolated `uv tool` / `pipx` environment), so **never add a key there expecting a user to change it**, and never
document one as configurable. The only configuration end-users have is the git-ignored local config file created by
`init-local-config` (§3.1), which their shell profile sources.

`AppProperties` reads the packaged file, and `get_property(key)` is the single accessor. An **optional** key that
the file does not ship — `release_tag_pattern` is the one example — must be read defensively: `get_property` raises
for an absent key, and in a light-weight command the singleton may not exist at all (see `resolve_tag_pattern`).

**`no_init` commands (§2.1) get none of this** — `AppProperties` is never built for them. They resolve packaged
files through `importlib.resources` and the constants below instead.

### 4.2.1 Package Constants (`src/mega_snake/constants.py`)

Shared literals live here; **never hardcode these strings**. Relevant to packaged-resource lookups:

| Constant                     | Value                    | Used for                                                     |
| ---------------------------- | ------------------------ | ------------------------------------------------------------ |
| `APP_NAME`                   | `"mgsnake"`              | The user-facing command name (help text, synopsis).          |
| `MODULE_NAME`                | `"mega_snake"`           | `importlib.resources.files(MODULE_NAME)` — the package root. |
| `RESOURCES_DIR` / `DOCS_DIR` | `"resources"` / `"docs"` | The packaged docs fragment directory.                        |
| `DOCS_FILE_SUFFIX`           | `".md"`                  | Fragment file extension.                                     |
| `DOCS_OUTPUT_FILE`           | `"COMMANDS.md"`          | Default target of `generate-docs`.                           |

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

| Helper                                                  | Use it for                                                                                                                                                                                                                                                                                                              |
| ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Repo.resolve_remote()`                                 | The repository's remote (`util/repo.py`). **Memoized on the class**: one `git remote`, and with several remotes the user is prompted only once no matter how many call sites ask. Returns `None` (with a warning) instead of raising when `git remote` fails, e.g. outside a repository. `Repo.reset()` exists for tests. |
| `Repo.require_remote()`                                 | Same, for commands that cannot work without a remote: raises `EnvironmentError(NO_REMOTE_MESSAGE)`. A repository without a remote is not a misuse of the CLI, so it is not a `ClickException`. This is the **single** place that message lives — do not re-raise your own.                                               |
| `ensure_working_path(decline_message=None)`             | Get `working_path`, offering to create it when missing (and excluding it from git right away), or raising `UserDeclinedError` when the user says no. Used by `working-env` and by every light-weight pre-flight wrapper.                                                                                                |
| `exclude_from_git(entries)`                             | Append `(entry, description)` pairs to `.git/info/exclude`. Idempotent; skips with a warning outside a git repository and creates the exclude file when missing.                                                                                                                                                        |
| `write_json_atomically(path, payload, sort_keys=False)` | Serialize JSON through a temporary file in the destination directory + `os.replace`. Leave `sort_keys` False when the key order is part of a published contract (the Jira projection). Used by the store and by `jira-issues`; never hand-roll a second one.                                                             |

**Anything that creates a folder under the repo must exclude it from git in the same step** — that is what
`ensure_working_path` does, and why nothing else should call `os.makedirs(working_path)` directly.

### 4.4 Persistent State (`src/mega_snake/util/store.py`)

The three pre-existing configuration layers are all read-only from the CLI's point of view: `config.properties`
ships in the wheel, `AppProperties` is a per-process singleton `_check_forbidden_execution` keeps immutable, and
`local_config_file`/`local_env_file` are a shell prelude the CLI writes once and never reads back. `Store` is the
missing middle piece — state the CLI both writes and reads.

| Scope | File | For |
|---|---|---|
| `repo` | `<git-dir>/mgsnake/state.json` | Per-clone settings (`jira.project_key`, `jira.board_id`, the field ids) |
| `global` | `~/.config/mgsnake/state.json`, `%APPDATA%\mgsnake\state.json` on Windows | User-wide settings (`jira.domain`, `jira.email`) |

Reads resolve **`env var > repo > global > default`**. The environment on top is deliberate: every workflow that
exported these variables before the store keeps working, so migration can be gradual.

Non-negotiables when touching this file:

- **Lazy, and independent of `AppProperties`.** Nothing is read until the first `get()`, which is what lets it
  work under all three initialization levels, `no_init` included.
- **No subprocess.** The repo scope is found by walking up the filesystem for `.git` (handling the `.git` *file*
  that worktrees and submodules leave), **not** through `run_operation` — that helper reads
  `get_property("shell")`, which requires the singleton `no_init` never builds. `exclude_from_git` already
  inspects `.git` directly, so this is the established precedent.
- **`.git/` and not `workspace_temp/`.** The latter is explicitly disposable (`diff-tree` wipes its subfolder on
  every run), and state that evaporates is not state. Living in `.git` also means no `.gitignore` or
  `.git/info/exclude` entry is needed.
- **Atomic writes** via `write_json_atomically` (§4.3): a `Ctrl-C` must never leave a corrupt JSON that then
  breaks every command.
- **Secrets are rejected, not warned about.** Any key matching `SECRET_KEY_PATTERN` raises `click.ClickException`
  and **nothing is written**. Tokens live in environment variables only: a plaintext credential in a state file
  is worse than an exported variable because it persists and is forgotten.
- **Keys are validated** against `KEY_PATTERN` (lowercase, dotted namespace), so the file stays navigable.
- **Corrupt JSON produces a message naming the path**, never a raw `json.JSONDecodeError`.
- `reset_instance()` exists for tests and after a `chdir` (both the paths and the contents are memoized), the
  same way `Repo.reset()` does.

---

## 5. Shell Integration & Deployment

### User Installation Flow

The user-facing steps are in `README.md` and are not repeated here. What matters for development is **what the
sourced init script does**, since almost every §7 behaviour depends on it:

- Exports `MEGA_SNAKE_SHELL`, without which full and light-weight initialization both refuse to run (§2.1).
- Defines `mgsnake` as a **shell function** wrapping the real executable, plus the private `__mgsnake_*` helpers it
  dispatches to (§7.4). The function is the only thing that can act on the shell-dispatch signals.
- Loads the local config file once, so it applies without a new terminal.

The package itself stays in the isolated environment `uv tool` / `pipx` created for it: nothing is added to the
user's active Python environment, and no virtualenv has to be activated to run a command.

### Local Development Setup

Prerequisites: Python 3.13 (the version in `.python-version`; the published package itself supports 3.12+) and the
`uv` package manager.

```bash
git clone <repo-url> && cd mega-snake
uv sync --all-extras                       # dependencies, dev extras included
uv run pytest                              # the suite, with the coverage gates of §6.2
uv build                                   # wheel
uv tool install dist/*.whl --force-reinstall
```

Then add the same init line end-users add (`README.md`) to your profile, restart the terminal, and check
`mgsnake --help`. Installing the wheel is only needed to exercise the **installed** entry point — the one thing
`uv run` cannot verify, and precisely where the exit-code contract of §7.2 lives.

### Releasing to PyPI (`.github/workflows/release.yml`)

Publication is automated and **gated**. Publishing a version to PyPI is irreversible — the number can never
be reused, even after deleting the file — so every check runs before the build and the job fails closed.

**Three facts must agree, or nothing is published:**

| Fact                 | Source                                   | Enforced by                                                         |
| -------------------- | ---------------------------------------- | ------------------------------------------------------------------- |
| Tag shape `vX.Y.Z`   | The git tag                              | Regex; `v0.1.5-beta`, `0.1.5` and `v1.2` are all rejected           |
| The released version | `[project] version` in `pyproject.toml`  | Must equal the tag with the `v` stripped                            |
| What changed         | A `## [X.Y.Z]` section in `CHANGELOG.md` | Must exist **and** carry content that is not the seeded placeholder |

**The trigger is `release: types: [released]`, not `push: tags`.** `released` fires only for
non-prerelease publications, so `mgsnake create-release p` (prerelease) never reaches PyPI while
`l` and `r` do. A tag-push trigger would publish prereleases.

**`CHANGELOG.md` is hand-written, and that is the point.** Merge commit subjects in this repository read
`Merge pull request #58 from azltechnologies/upgrade`, which tells a user nothing. The exhaustive commit
list already exists in the GitHub Release body (`gh release create --generate-notes`, which `create-release`
passes); `CHANGELOG.md` is the curated half, written for people who install `mgsnake`. **Adding a
`## [X.Y.Z]` section is part of the change that bumps the version**, not a release-day chore.

Do not weaken the changelog gate into "the file grew" — a blank line satisfies that, which is precisely the
weak-assertion failure mode the testing principles warn about. The check verifies the _specific_ section
exists and says something.

**twine's role.** `uv publish` uploads; it does not validate metadata or render the README. `twine check`
does, and a README that fails to render on PyPI cannot be fixed without burning the version number, so it
runs on the built distributions before the upload. That is the only reason twine is a dev dependency — see
the load-bearing floor comment in `pyproject.toml`.

**Required secret:** `PYPI_API_TOKEN`, consumed as `UV_PUBLISH_TOKEN`. (PyPI Trusted Publishing via OIDC
would remove the stored token entirely and is the natural upgrade.)

---

## 6. Development Rules

### 6.1 Code Quality Standards

**ALL code must follow these standards without exception:**

1.  **Type Hinting - MANDATORY for all functions and parameters:**
    - **All function parameters** must have explicit type annotations (e.g., `name: str`, `count: int`)
    - **All function return types** must be explicitly declared (e.g., `-> str`, `-> None`, `-> list[str]`)
    - **Use `Optional[T]`** for optional types instead of `T | None` (e.g., `Optional[str]` not `str | None`)
    - Example:
      ```python
      def process_data(items: list[str], timeout: Optional[int] = None) -> dict[str, int]:
          """Process items with optional timeout."""
          pass
      ```

2.  **Docstrings - MANDATORY for all modules, classes, and functions:**
    - **Module-level docstring**: Must be at the top of every `.py` file
    - **Class docstring**: Required for all class definitions
    - **Function/method docstring**: Required for every function and method (including `__init__`, `__str__`, etc.)
    - **Format**: a summary line, then `Parameters:`, `Raises:` and `Returns:` — all three always present, with
      `None` spelled out when a section is empty:

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
      ```

3.  **Imports**: Group imports in this order:
    - Standard Library
    - Third Party
    - Local Application
    - Each group separated by a blank line

4.  **Error Handling** — see §7 for the full exit-code contract. In short:
    - Raise `click.ClickException` **only when the user invoked the command incorrectly**. A missing
      tool, an unconfigured remote or a declined prompt is not misuse; those get their natural
      exception type instead.
    - Raise `ValueError` for an invalid value, and the matching built-in for everything else
      (`FileNotFoundError`, `PermissionError`, …) so `ERROR_CODES` can resolve a meaningful status.
    - Raise `InternalStateError` **only** where reaching the line means `mgsnake` is defective —
      typically a state an earlier graceful check already ruled out. Never use it for anything the
      user or their environment can legitimately cause, and never use a built-in for a real bug.
      See §7.6, which is the full rule and its rationale.
    - Never use `assert` for either. It is stripped by `python -O`, which deletes the check.
    - Let unexpected errors bubble up. `main()` in `__main__.py` — **not** `cli()` — is the single
      place an exception becomes an exit code.
    - **Every new custom exception must be registered in `ERROR_CODES` in the same change.** A test
      walks the package and fails naming any that is not.

5.  **Paths**: Always use `pathlib.Path` or `os.path` joins. Never use string concatenation for paths.

6.  **Language**: All code comments, docstrings, and identifier names (variables, functions, classes, etc.) must be
    written in English, regardless of the language used to discuss the task. This is an English-speaking work
    environment.

7.  **Avoid duplicated code**: Each fix, implementation or modification in the codebase must use the existing utilities, helpers, and patterns. Additionally, If you find yourself copying and pasting code, consider refactoring it into a shared utility function or class.

    **Prefer existing third-party dependencies over adding new ones.** Before introducing a new library, check
    whether any dependency already listed in `pyproject.toml` can do the job. Adding a new package incurs
    maintenance, security, and version-compatibility costs for every future contributor; only do it when the
    existing set genuinely cannot cover the need. The same rule applies to standard-library modules: reach for
    what is already imported in the module before pulling in something new.

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
# Run the full test suite with coverage reporting
uv run pytest

# This generates:
# - report.html: HTML report of test results
# - coverage_html/index.html: detailed coverage breakdown by file
# - and fails the run when overall coverage drops below 95% (--cov-fail-under)
```

The 98% floor for new or modified code is **not** enforced by the runner — only the 95% overall gate is. Read
`coverage_html/index.html` for the files you touched and check them yourself; the suite going green says nothing
about the lines you just added.

The test file mirrors the source path: `config_environment/java_set.py` → `src/tests/config_environment/test_java_set.py`.

#### Coverage is not evidence of verification

A line at 100% coverage has been **executed**, which says nothing about whether its result was **checked**. Before
calling a test done, ask what incorrect value that line could produce with every assertion still green — if such a
value exists, the assertion is too weak. See `.github/instructions/testing_principles.instructions.md` for the full
checklist; it is binding, not advisory.

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

**What goes in a fragment (follow the shape the existing fragments already use):**

| Part                 | Content                                                                                                                                                                |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Opening paragraph(s) | The **why**: the problem the command solves, or the design decision behind it ("the zero-config start command", "pipeline via files"). Never a restatement of `help=`. |
| `## Output`          | Every file or folder the command writes, with its path, and what each one contains. Required whenever the command touches disk.                                        |
| `## Examples`        | Real invocations in a fenced block, when the argument shape is not obvious from the synopsis.                                                                          |
| `## Notes`           | Preconditions (needs a remote, needs `pom.xml`), destructive behavior, locale/platform caveats, and interactions with other commands.                                  |

**Enforcement — four tests in `src/tests/docs_gen/test_docs_gen.py`, parametrized over every command:**

1. `test_every_command_has_a_fragment` — a new command without a fragment turns the suite red, naming the command.
2. `test_no_orphan_fragments` — a renamed/deleted command must not leave a stale `.md` behind.
3. `test_every_documented_command_uses_explicit_help` — compares `cmd.help` against `inspect.getdoc(callback)` so an
   omitted `help=` (which Click silently fills from the docstring) is caught.
4. `test_epilog_never_repeats_generated_content` + `test_fragment_never_repeats_the_epilog` — the no-duplication rule
   above, checked mechanically instead of by convention.

Plus `mgsnake generate-docs --check`, which catches a committed `COMMANDS.md` that no longer matches the code. The
tests and the check catch _different_ failures: the tests catch missing/duplicated prose, the check catches a stale
generated file. **After changing any command metadata, run `mgsnake generate-docs` and commit the regenerated
`COMMANDS.md` in the same change.**

### 6.4 Formatting (`ruff format`) — the last step before a commit

**Every commit must carry formatted code, and the formatting runs _after_ the suite is green, never before.**
The order is the rule:

```bash
uv run pytest          # 1. all tests pass, coverage thresholds met
uv run ruff format     # 2. only then, format
uv run ruff check .    # 3. lint still clean, and commit
```

**Why formatting comes last.** Code that is still failing its tests is code that is still being rewritten, so
formatting it early only means formatting it twice, and it mixes reflowed lines into the diff you are trying to
read while debugging. Running it once, on the final shape of the change, keeps the formatting noise in a single
pass and keeps the review diff about the behaviour that changed. It is also the only order in which a green run
means anything: the suite you saw pass is the code you are committing, modulo formatting only.

**Why the author has to remember it.** CI runs `ruff check src/mega_snake` (lint) and never `ruff format --check`,
so unformatted code merges silently — nothing is going to catch this for you. That is exactly how the repository
accumulated a backlog of files that predate the rule.

**Scope.** `[tool.ruff]` in `pyproject.toml` sets `include = ["src/**/*.py"]` and excludes `src/tests`, so the
formatter covers `src/mega_snake` only. Test files are outside its scope and must not be reformatted into a
change.

**Format the files your change already touches — do not sweep unrelated ones into a feature PR.** A bare
`uv run ruff format` reformats every file that predates this rule, which buries the actual change under unrelated
reflows and makes the PR unreviewable. Clearing that backlog is legitimate work, but it belongs in a commit of its
own that does nothing else.

### 6.5 Keeping this file honest

No test can check the prose in this document, so it decays silently — and a rule that no longer describes the code
is worse than no rule, because it is followed anyway. Whenever a change makes a statement here false, apply one of:

1. **Update it** — the principle still holds, only the implementation moved.
2. **Generalize it** — the specific situation is gone, but the anti-pattern it warned about can recur. Rewrite the
   warning as a standing rule and drop the anecdote. Exhaust this option before reaching for the third.
3. **Delete it** — it contradicts how the project works now, and there is no lesson left to keep.

Two habits keep the decay slow: **never restate what is generated or enforced elsewhere** (`COMMANDS.md`,
`--help`, a named test), cite it instead; and **prefer the rule to the story of how it was learned** — a
war story ages, an imperative does not.

---

## 7. Exit Codes & the Shell-Dispatch Signals

The status `mgsnake` leaves behind is part of its public interface: a shell function and CI steps branch on it.
Treat this section as a contract, not as documentation of an implementation detail. It is also the part of the
design that rots most quietly: exit-code plumbing can be fully written and never actually reached, with every
error condition silently exiting `1` while the tests stay green. **Only a test that asserts the real number
proves any of it works** (§7.5).

### 7.1 The table

| Code        | Meaning                                                                                   | Mechanism                                                                      |
| ----------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| `0`         | Success                                                                                   | Default                                                                        |
| `1`         | The user invoked the command incorrectly                                                  | `click.ClickException`                                                         |
| `2`         | Malformed invocation / programming error in command registration                          | `click.UsageError`                                                             |
| `29`        | Success **+ the shell must re-source the local config file**                              | The shell-dispatch signal, §7.4                                                |
| `30`        | Success **+ the shell must load an env file**                                             | The shell-dispatch signal, §7.4                                                |
| `100`       | A bug in `mgsnake`: a declared broken invariant, or an internal error with no mapped type | `InternalStateError` (§7.6) / `WorkspaceError` default (`INTERNAL_ERROR_CODE`) |
| `101`–`112` | Error, by exception type                                                                  | `ERROR_CODES`                                                                  |
| `113`       | A validation reported stale or invalid content                                            | `ValidationError`                                                              |
| `114`       | The user declined a required action                                                       | `UserDeclinedError`                                                            |
| `115`       | `VersionSetException`                                                                     | `ERROR_CODES`                                                                  |

`105` is deliberately vacant: it used to be assigned to `IOError`, which **is** `OSError` — the same object
`EnvironmentError` aliases — so the two entries collided and one of them was always unreachable. Do not fill the
gap by re-adding an alias of a type already in the table.

**`ClickException` is about invocation, not blame.** A missing tool, an unconfigured remote or a declined prompt is
not misuse — the user broke no contract — so those must **not** be `ClickException`s. `require_remote` raises
`EnvironmentError`, the `osv-scanner` guard raises `FileNotFoundError`, `ensure_working_path` raises
`UserDeclinedError`, and `write_or_check_document` raises `ValidationError`. What legitimately stays a
`ClickException` is a genuine invocation error: mutually exclusive flags (`diff-tree`, `create-release`), an unknown
command name (`man`, `__main__`).

`ValidationError` and `UserDeclinedError` subclass `click.ClickException` on purpose: they keep the clean,
traceback-free output Click gives a user error and only change the number.

### 7.2 How a code actually reaches the shell

Three links in one chain. Breaking any of them silently collapses every status back to `1`, so understand each
before touching it.

1. **`[project.scripts]` points at `main()`, never at `cli`.** The installed executable calls that symbol directly,
   so a translation living anywhere else (in a `if __name__ == "__main__"` block, say) runs only under
   `python -m mega_snake`, which no user ever types.
2. **`main()` is the only place an exception becomes an exit code.** It re-raises `click.ClickException` untouched —
   Click already knows its `exit_code`, and wrapping it would relabel a user error as an internal one — and wraps
   everything else in `WorkspaceError`, whose `__init__` resolves the status and installs `_on_crash` as the except
   hook. `SystemExit` is a `BaseException`, so the reload signal passes straight through.
3. **`_on_crash` delivers it.** `sys.exit()` called from inside an except hook _does_ set the process status; that is
   the mechanism the whole design rests on. It must exit for **every** `WorkspaceError`, the unmapped `100`
   included: returning without exiting hands the process back to Python's default handling and its status of `1`,
   which would make `100` the one code that can never be observed.

**Never convert an exception into `SystemExit(e)`.** `SystemExit` uses its argument as the status _only when it is
an `int`_; given an exception it prints it and exits `1`, flattening every failure to the same number. `cli()`
re-raises with the type intact instead.

### 7.3 Registering a new exception — mandatory

**Every custom exception introduced in this package must be registered in `ERROR_CODES` in the same change**, or —
for a `click.ClickException` subclass — must declare its own `exit_code`. `test_every_custom_exception_in_the_package_has_a_registered_exit_code`
walks the package and fails naming any that is not, so this is enforced mechanically rather than by convention.

The single documented exception is `InternalStateError` (§7.6), which is listed in that test's `UNMAPPED_BY_DESIGN`
because `INTERNAL_ERROR_CODE` already carries its exact meaning. Adding a second name to that set needs the same
kind of argument, not just the wish to skip the registration.

The table lives in `util/formatting.py`. A type owned by a module `formatting.py` cannot import (because that module
already imports `formatting`) registers itself at its definition site instead — see `VersionSetException` in
`config_environment/models/tools_version.py`.

Lookup goes through `resolve_error_code`, which **walks the MRO**: an unlisted subclass inherits its nearest listed
ancestor's code (`subprocess.CalledProcessError` → 111), while a type listed in its own right still wins over its
ancestor (`FileNotFoundError` → 102, not the 112 of the `OSError` it derives from). Never narrow this back to an
exact `type(e) in ERROR_CODES` lookup: it sends every unlisted subclass to the generic `100`.

### 7.4 The shell-dispatch signals (`29`, `30`) — what they do and who consumes them

**What they do:** they ask the user's shell to perform something Python cannot. A child process cannot mutate its
parent's environment — an OS guarantee, not a Python limitation — so anything that changes the caller's variables
has to run _in the caller's session_. The command's exit status is the request; the shell is what performs it.

| Code | Request                         | Emitted by                                                                                                                                          |
| ---- | ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `29` | Re-source the local config file | `@cli_metadata(reloads_environment=True)`, and the `reload-config` command. It depends on the `local-config-path` command to locate the config file |
| `30` | Load an env file                | The `load-env` command. It depends on the `local-env-path` command to locate the env file                                                           |

**Who consumes them:** the `mgsnake` **shell function** defined by `config_setup.sh` / `config_setup.ps1`. It calls
the real executable through `command mgsnake` (bash/zsh) or the resolved application path (PowerShell), captures the
status, and dispatches to a private `__mgsnake_*` helper. There is no recursion — `command` and the resolved path
both bypass the function — and the only visible difference is that `type mgsnake` reports a function.

```bash
mgsnake() {
    command mgsnake "$@"
    local exit_code=$?
    case "$exit_code" in
        "$MEGA_SNAKE_RELOAD_EXIT_CODE")
            __mgsnake_reload
            return 0 ;;
        "$MEGA_SNAKE_LOAD_ENV_EXIT_CODE")
            env_file=$(__mgsnake_args_after "$MEGA_SNAKE_LOAD_ENV_COMMAND" "$@")
            __mgsnake_load_env "$env_file"
            return 0 ;;
    esac
    return "$exit_code"
}
```

**A served signal is reported to the caller as `0`, and this is part of the contract.** The signal is a _request_;
once the wrapper has carried it out there is nothing left to tell the caller, and propagating it would mean every
environment command looks like a failure — `mgsnake set-java && echo ok` would never print, and a `set -e` script
would abort on the happy path of `mgsnake load-env`, contradicting the advice in `load-env.md` to load an optional
`.env` unconditionally from a startup script. Every _other_ status is passed through untouched, and a direct
invocation that bypasses the function (`command mgsnake load-env`) still sees the raw `29`/`30`, which is what the
CLI-level tests assert. `test_bash_wrapper_reports_success_once_it_has_served_the_signal` and its pwsh twin pin the
caller-visible status **and** the dispatch marker, so a wrapper that returned `0` without doing the work fails too.

**How arguments reach the shell — and why not stdout.** `load-env` takes a file path, which the helper needs. The
obvious channel is stdout (`$(...)`, the way `direnv` and `ssh-agent` do it), and it was rejected: it makes the
command's stdout a data channel, so _any_ helper that ever prints there silently corrupts the value, at a distance,
only at some log levels. Instead `__mgsnake_args_after` rescans the wrapper's own `"$@"`, drops everything up to
the command name, and forwards what follows. Forwarding the raw `"$@"` would hand the global options to the helper
(`mgsnake --log-level DEBUG load-env foo.env`), and parsing them in shell would mean reimplementing click.

Two consequences of locating the command **by name**:

- **These commands must not have aliases.** An alias resolves fine and returns the right status, then leaves the
  wrapper unable to find the name — so it would load `.env` instead of the requested file, with no error at all.
  `test_shell_backed_commands_have_no_aliases` pins this.
- **The name is hard-coded in three places** (`constants.py`, and both scripts), like the numbers themselves.

**The helpers are private, and must stay that way.** `__mgsnake_reload`, `__mgsnake_load_env` and
`__mgsnake_args_after` are implementation detail; the public interface is `mgsnake reload-config` and
`mgsnake load-env`, documented like any other command. Exposing a helper under its own public name gives every
action two names, one of them undocumented and invisible to `--help`. The single caller allowed to invoke a helper
directly is the local config file generated by `init-local-config`: it is _being sourced by the shell_, so
`LOAD_ENV_HELPER` already reaches the right session, and routing it back through the CLI would mean exiting `30`
from inside a reload the wrapper is currently performing.

**The no-argument fallback belongs to the user, not to startup.** `mgsnake load-env` with no argument resolves to
the local environment file (`.mgsnake.env` under `workspace_temp`, via `local-env-path`) and falls back to `.env`
in the current directory when that does not exist — a deliberate, temporary behavior (see `load-env.md`) slated
for removal once a persistence layer lets the user toggle it. **The startup call at the bottom of
`config_setup.sh` / `config_setup.ps1` must never take that branch**: resolving the path there is what stops a
terminal opened in a directory with an unrelated `.env` from exporting it, unfiltered and unasked, into the
session. So the startup line passes the path explicitly
(`__mgsnake_load_env "$(command mgsnake local-env-path)"` in bash,
`__mgsnake_load_env -Path (& $global:MegaSnakeExe local-env-path)` in PowerShell), and
`test_scripts_resolve_the_env_file_explicitly_at_startup` pins it so it cannot regress to the bare call.

**Open question for the persistence layer.** `init-local-config` writes a `LOAD_ENV_HELPER` line into the config
file it generates, so the local environment file can be loaded **twice** per terminal: once when `__mgsnake_reload`
sources that file, and again by the startup line. It is harmless (the parser is idempotent) but undocumented.
Whichever toggle the persistence layer introduces has to decide between keeping the redundant call, skipping it
when the config file already loaded the same path, or dropping the embedded line from newly generated files.

**Whenever you change how the CLI is invoked, re-check the wrapper.** The signal only works while something
captures the executable's status; a wrapper that stops doing so leaves the Python side emitting codes into a void,
and nothing fails loudly when that happens.

**Emitting `29` from a normal command:** declare `@cli_metadata(reloads_environment=True)`, and the
`config_environment` module wrapper relays it into `ctx.obj["exit_code"]`; `post_command` turns that into the
process status. It is per command, **not** per module: living in `config_environment` is not what makes a command
change the environment, touching those files is.

| Command                                 | Emits `29` |
| --------------------------------------- | ---------- |
| `init-local-config`, `working-env`      | Yes        |
| `set-java`, `set-gradle`, `set-maven`   | Yes        |
| `maven-project-setup`, `graphql-schema` | No         |

Everything shared across the language boundary is pinned by `src/tests/light_weight/test_shell_wrapper.py`: the two
numbers, the command name the scripts scan for, the helper name the generated config file calls, the absence of
aliases, and the argument slicing itself — run through a real `bash` rather than asserted as text.

### 7.5 Testing rule

`src/tests/test_exit_codes.py` holds one test per row of the table above. Two rules it exists to enforce:

- **Assert the exact number, and assert what it is _not_.** A bare "it failed" assertion is satisfied by the silent
  fallback to `1`, so it cannot distinguish a working contract from a broken one. Every row asserts `== <code>`
  **and** `!= 1`.
- **Use the right level.** `CliRunner` for anything decided inside the click group (the reload signal, a
  `ClickException`'s own `exit_code`). `subprocess` for anything decided _outside_ it — the translation in `main()`
  and the except hook. `CliRunner` catches exceptions and reports `1` for all of them, so an in-process test of the
  hook would assert nothing at all.

### 7.6 `InternalStateError` — the only exception that means "this is our bug"

**`InternalStateError` may be raised in production code only where reaching the statement means `mgsnake` itself is
defective.** Anything else must be typed to the built-in that actually describes it, so `ERROR_CODES` resolves a
meaningful status. This is a rule about _provenance_, not about how bad the situation looks.

**The test that decides it.** Ask: _could a correct build of `mgsnake`, running in a reasonable environment, reach
this line?_

| The situation was…                                                                                                                                                 | Then it is…   | Raise                                                                                                                               |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| already ruled out upstream — a resource validated during initialization, a value this package itself produced, a branch a previous graceful check made unreachable | **a bug**     | `InternalStateError`                                                                                                                |
| external, but from a vocabulary we committed to mirroring in full — a `git diff --raw` status letter, an OS we claim to support                                    | **a bug**     | `InternalStateError`                                                                                                                |
| never ruled out — a missing tool, an unconfigured remote, absent input, a file the user supplies or hand-edits, a declined prompt                                  | **not a bug** | the specific built-in (`FileNotFoundError`, `EnvironmentError`, `ValueError`, `subprocess.SubprocessError`, `UserDeclinedError`, …) |

The sharpest form of the first row, and the one that recurs: **a caller already did a graceful
`ws_warning(...) + return` for the empty/missing case, and the callee re-checks it anyway.** That second check is
unreachable by design — `select_version`'s empty list is exactly this, since all three of its callers return early
when the system has no version installed. Reporting it as an environment problem would send the user hunting for
something to install when the real defect is in the flow above.

**"External" is not the same as "not our fault."** The second row is the subtle one: `FileType.from_symbol` receives
a status letter straight from `git diff --raw`, so the value is external — yet the enum exists precisely to mirror
git's full set of status letters. If git grows one we never added, keeping up with it was our job. The question is
never _where did the value come from_, it is _whose job was it to handle this value_. Contrast with
`_validate_commit`, which also inspects git output but is checking a reference **the user typed**: a bad one there
is input, not a gap in our coverage.

**Why a dedicated type instead of `assert`.** `assert` is stripped by `python -O`, which removes the guard silently
and lets the failure resurface later as something unrelated. It also leaves the message as the only thing
distinguishing a bug from an environment failure — a distinction that disappears the moment someone rewrites the
raise. The type carries it instead.

**Why not a plain built-in either.** That is the failure this rule exists to prevent: retyping these to
`FileNotFoundError`/`ValueError` makes them exit `102`/`103`, indistinguishable from a genuine missing file or bad
value, and tells the user to fix something they neither caused nor can reach.

**Mechanics.**

- It does **not** subclass `click.ClickException`. Those exist to give a user error clean, traceback-free output; a
  bug wants the traceback, and `_on_crash` prints one for `INTERNAL_ERROR_CODE`.
- It is **deliberately absent from `ERROR_CODES`**, listed instead in `UNMAPPED_BY_DESIGN` in
  `src/tests/test_exit_codes.py`. It inherits `100` from `resolve_error_code`'s default, which already means exactly
  this. Registering it would put `100` among the table's values, and a status a registered type shares with the
  unmapped fallback carries no information the fallback did not already carry. **This is the one documented
  exception to §7.3** — every _other_ custom exception still needs its own entry.
- **Catching it is legitimate where the "impossible" state is actually expected.** `resolve_tag_pattern` catches it
  around `get_property`, because `create-release` is light-weight and the properties singleton genuinely may not
  exist there. That is the mirror image of the rule: same condition, different flow, different verdict.
