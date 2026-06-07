# GitHub Copilot Instructions for `unix-scripts` (CodeName Snake)

## 1. Project Overview & Philosophy

`codename_snake` is a robust Python 3.13+ CLI tool designed to standardize the local development lifecycle. It acts as a "Swiss Army Knife" for developers, primarily automating the complex configuration of VS Code environments for Java/Gradle, but extending into Git management, Release orchestration context, and Google Cloud observability.

**Core Philosophy:**
- **Zero Config Start**: A developer should be able to run `snake createWorkingEnv` and have a fully functional IDE state immediately.
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

### 2.1 Entry Point & CLI Orchestration (`src/codename_snake/__main__.py`)

The application uses a `click.Group` with a custom `CliGroup` class to support command aliases. The entry point `cli()` function initializes global application properties before any command runs.

**Critical Pattern: Initialization & Light-weight Mode**
The CLI checks for a `skip` flag in command metadata. If present, it bypasses heavy environment checks (like requiring a valid workspace folder), allowing "light-weight" commands (e.g., `createRelease`) to run anywhere.

```python
# src/codename_snake/__main__.py
@click.pass_context
def cli(ctx: click.Context, log_level: str, shell: str) -> None:
    # ...
    # Access metadata to check for 'skip' flag
    metadata = getattr(cmd.callback, "flags", {})
    if flags and "skip" in flags:
        # Light-weight mode: minimal initialization
        init_app_properties(log_level, shell, light_weight=True)
```

### 2.2 Command Registration & Aliases (`src/codename_snake/util/cli_group.py`)

We do not standard `click` alias implementation. We use `CliGroup` to register commands with multiple names.

**Usage:**
```python
# Registration in __main__.py
from .diff_tree.module import main as diff_tree
# Registers 'diff_tree' command accessible via 'dt' and 'tree' aliases
cli.add_command_with_alias(diff_tree, ["dt", "tree"])
```

### 2.3 The Wrapper Pattern (`module.py` files)

Each functional module (e.g., `config_environment`) exposes an `add_wrapper` decorator. This allows module-specific checks to run before the command execution, keeping the core logic clean.

**Example from `src/codename_snake/config_environment/module.py`:**
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

---

## 3. Core Functional Modules

### 3.1 Environment Configuration (`src/codename_snake/config_environment/`)

This is the most complex module, responsible for generating `.code-workspace` files. It configures the "settings" section of the workspace file directly, avoiding reliance on `.vscode/settings.json`.

#### `createWorkingEnv`
- **Logic**: 
    1. Validates Git repository status.
    2. Loads local developer overrides (`initial_load`).
    3. Configures Java (`set_java`) and Gradle (`set_gradle`).
    4. Generates VS Code tasks, launch configurations, and recommendations.

#### `setJava` (`java_set.py`)
Manages the `java.configuration.runtimes` and `terminal.integrated.env` settings in VS Code.

**Key Logic:**
- It parses the `.code-workspace` file (as JSON with comments).
- It queries the OS for installed JDKs.
- It updates the `settings` structure inside the workspace file to point `JAVA_HOME` to the selected version.

```python
# src/codename_snake/config_environment/java_set.py
ENV_VARIABLE = f"terminal.integrated.env.{OS_MAP[OS]}"
JAVA_JQ_QUERY = f'.settings["{ENV_VARIABLE}"].JAVA_HOME'

# It uses python logic to traverse the JSON structure similar to JQ
# to find and replace the Java path.
```

#### `setGradle` (`gradle_set.py`)
Like `setJava`, this configures the Gradle version for the workspace.

**Key Logic:**
- It identifies installed Gradle versions via `ToolVersion` abstraction.
- It updates `java.import.gradle.home` and `terminal.integrated.env` settings.
- It ensures consistency between the terminal environment and the IDE's internal Gradle wrapper.

**Technical Note: JSON with Comments**
Both `setJava` and `setGradle` modify the `.code-workspace` file which contains comments. The standard python `json` library fails on comments. We use a custom `load_json_with_comments` utility to handle VS Code's configuration format safely without stripping comments, which are vital for developers understanding the config.

#### `initLocalConfig` (`local_config.py`)
Creates a local developer-specific configuration file that is **ignored by Git**.

**Why?**
Developers often have machine-specific tokens, paths, or aliases that shouldn't be committed to the repo. `initLocalConfig` generates a shell-specific file (`.sh` or `.ps1` logic embedded) that is sourced by the main environment. This pattern allows the tool to support "Convention over Configuration" while still allowing for "Configuration" when necessary.

### 3.2 Git Utilities (`src/codename_snake/diff_tree/`)

#### `createDiffTree` (`dt`)
Generates a visual tree representation of changed files.

**Implementation Details:**
- Uses `git diff-tree -r {main_branch} {current_branch}` to get raw file lists.
- categorizes files using `FileType.from_symbol(symbol)`.
- Reconstructs a dummy directory structure in `workspace_temp/diff_tree_dummy_repo`.
- Uses `directory_tree` library to generating the visual text tree.

```python
# src/codename_snake/diff_tree/module.py
for diff in diff_str.split("\n"):
    columns: list[str] = diff.split("\t")
    symbol = columns[0].split(" ")[4] # M, A, D, etc.
    path: str = columns[1]
    # builds tree structure...
```

### 3.3 Remote Branch Management (`src/codename_snake/remote_branches/`)

#### `remoteBranchesDetails`
Analyzes remote branches to suggest cleanup candidates.

**Filtering Logic (`-f` flag):**
- **'M' (Merged)**: Branches that have been merged into `master`.
- **'U' (Unmerged)**: Branches with unique commits not in `master`.
- **'A' (All)**: Both.

It creates `workspace_temp/remote_branches.txt` containing detailed metadata (author, last commit date, ahead/behind count) for every branch.

#### `remoteBranchesCleanUp`
An interactive tool that consumes the output of `remoteBranchesDetails`.

**Logic:**
1. Allows re-running `remoteBranchesDetails` to refresh data.
2. Reads `workspace_temp/remote_branches.txt`.
3. Presents an interactive list to the user to select branches for deletion.
4. Performs `git push origin --delete <branch>` and prunes local references.

**Design Pattern: Pipeline via Files**
Instead of passing complex objects between commands in memory, we use the filesystem (`remote_branches.txt`) as an intermediate buffer. This allows the user to inspect (and potentially edit) the list of candidates before running the destructive cleanup command.

### 3.4 Release Management (`src/codename_snake/light_weight/create_release.py`)

Automates GitHub releases, creating tags and proper GitHub Release entries.

**Arguments:**
- `tag_suffix`: e.g., `v1.0.0-{suffix}`
- `release_type`:
    - `p`: Prerelease (`--prerelease`)
    - `l`: Latest (`--latest`)
    - `r`: Replace Latest (Updates the `latest` tag to point to a new commit)

**Logic:**
It fetches the current tags, calculates the new tag based on the suffix, and relies on the `gh` CLI to publish the release.

**Technical Note: Why use the `gh` wrapper?**
We use the `gh` (GitHub CLI) tool because it leverages the user's existing authentication state, avoiding the need to manage complex API tokens within the Python code.

```python
    # src/codename_snake/light_weight/release_handler.py
    cwd: str = (
        f'gh release create {tag_name} {release_type} --target "{release_branch}" '
        f'--title "{tag_name}" {release_notes} --generate-notes'
    )
```

**Educational Logic:**
Instead of re-implementing the GitHub API client (which requires managing OAuth tokens, permissions, etc.), we delegate the heavy lifting to the `gh` binary. This is a common "shell wrapper" pattern where Python manages the *control flow* and *validation*, but the shell executes the *remote action*.

### 3.5 Other Utilities

#### `createGraphqlSchema` (`graphql_schema.py`)
Compiles multiple `.graphql` files into a single schema and generates introspection JSON.

**Why introspection?**
Frontend tools (like Apollo) and IDE plugins often require a full introspection result (`schema.json`) to provide autocompletion and type checking, not just the raw SDL string.

#### `expiredCertsJks` (`jks_expired_certs.py`)
Audits Java KeyStore (JKS) files for expired certificates using `keytool`.

**Technical Challenge:**
Parsing the output of `keytool -v -list` is non-trivial because the date format depends on the system locale and standard Java output formats. The tool attempts to parse these formats to warn developers before their local dev environments break due to expired SSL certs.

#### `msg` (`echo.py`)
Exposes the internal logging mechanism to the shell. Used by `config_setup.sh` to print consistent success/error messages from shell scripts.

---

## 4. Utilities & Helpers

### 4.1 Output Formatting (`src/codename_snake/util/formatting.py`)

** STRICT RULE**: NEVER use `print()`. Always use valid logging/formatting functions.

- `ws_info(msg)`: ℹ️ Blue info message.
- `ws_success(msg)`: ✅ Green success message.
- `ws_warning(msg)`: ⚠️ Yellow warning.
- `ws_error(msg)`: ❌ Red error.
- `ws_advice(msg)`: 💡 Helpful tip/advice.

### 4.2 Property Management (`src/codename_snake/util/props.py`)

Configuration is layered:
1. **Hardcoded Defaults**
2. **`src/config.properties`**: Static project config (versions, default paths).
3. **Local Overrides**: A local file (usually ignored by git) that overrides specific keys for a specific developer machine.

Access properties via `get_property(key)`.

### 4.3 Shell Execution (`src/codename_snake/util/util.py`)

Use `run_operation` for ALL shell commands. It handles logging, error capturing, and return codes.

```python
result = run_operation(
    command="git fetch --all", 
    message="Fetching remotes" # This is logged to console/file
)
if result.returncode != 0:
    # handle error...
```

---

## 5. Shell Integration & Deployment

### User Installation Flow

When end-users install `codename_snake` via `uv tool install` or `pipx install`:

1. The package is installed in an isolated virtual environment.
2. The `snake` command becomes available globally.
3. Users add initialization code to their shell profile:
   - **Bash/Zsh**: `. "$(snake shell-path bash)"` → outputs the path to `config_setup.sh`
   - **PowerShell**: `. (snake shell-path pwsh)` → outputs the path to `config_setup.ps1`
4. The initialization script (`config_setup.sh` or `config_setup.ps1`) is sourced, which:
   - Sets `CODENAME_SNAKE_SHELL` environment variable
   - Defines `snake_reload` to (re)load the local config file (if present)
   - Calls `snake_reload` once so the local config is applied immediately
**Why this approach?**
- Allows the tool to run anywhere without polluting the user's active Python environment
- Users don't need to manually activate/deactivate virtual environments
- The `snake` function transparently manages venv switching
- Multiple concurrent shells can each have their own active venv state

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
   - **Bash/Zsh**: Add `. "$(snake shell-path bash)"` to `~/.bashrc` or `~/.zshrc`
   - **PowerShell**: Add `. (snake shell-path pwsh)` to your PowerShell profile

6. Restart your terminal and verify:
   ```bash
   snake --help
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

