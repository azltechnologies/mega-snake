# Mega `Snake`

A development environment automation platform for teams using **Java/Gradle in VS Code**. It creates consistent local setups, shell configuration, and workspace tooling so developers can start coding quickly without repeating manual environment setup.

## Why Mega Snake?

New contributors often lose time on first-day setup: matching Java and Gradle versions, configuring VS Code correctly, and wiring repetitive local scripts. Mega Snake solves this by automating the same environment steps for everyone.

- **Start faster:** bootstrap a ready-to-code Java workspace in VS Code with one CLI flow.
- **Reduce setup drift:** keep local Java/Gradle/tooling configuration consistent across developers.
- **Automate recurring tasks:** run common Git, release, and utility workflows from one CLI.

## Installation

### Via PyPI (Recommended for End Users)

Install `mega-snake` from PyPI using either `uv` or `pipx`:

**Using uv:**

```bash
uv tool install mega-snake
```

**Using pipx:**

```bash
pipx install mega-snake
```

### Post-Installation Setup

After installation, add the shell initialization script to your shell configuration:

**For bash/zsh**, add this line to `~/.bashrc` or `~/.zshrc`:

```bash
. "$(mgsnake shell-path bash)"
```

**For PowerShell**, add this line to your PowerShell profile (usually `$PROFILE`):

```powershell
. (mgsnake shell-path pwsh)
```

Then restart your terminal or source the configuration file to activate the `mgsnake` command.

## Usage

### Terminal Support

   The `mgsnake` CLI works on:

- Windows: PowerShell
- macOS/Linux: bash or zsh

### Basic Usage

   After installation and shell profile configuration, use the `mgsnake` command:

      ```bash
      # Show help
      mgsnake --help

      # Execute commands with specific log level
      mgsnake --log-level DEBUG <command>
      ```

### Log Levels

   Available log levels (from least to most verbose):

- ERROR: Only errors
- WARNING: Errors and warnings
- INFO: Normal operational messages (default)
- DEBUG: Detailed information for debugging
- NOTSET: All messages

### Example Commands

      ```bash
      # Create a working environment
      mgsnake working_env

      # Check GraphQL schema
      mgsnake graphql_schema

      # Show branch details with debug info
      mgsnake --log-level DEBUG remote_branches_details
      ```

   > **Note**: Each command has its own help. Use `mgsnake <command> --help` for specific details.

### Prefer command aliases for daily use

Many command names are intentionally descriptive. For faster terminal workflows, use aliases shown next to each command in this README.

```bash
# Full command
mgsnake working_env

# Alias
mgsnake cwe
```

### Available Commands

#### Environment & Configuration

##### `mgsnake working_env` (aliases: `cwe`, `env`, `createWorkingEnv`)

Sets up a complete VSCode workspace configuration for Java development:

- Creates/updates VSCode workspace file with recommended settings
- Configures git exclusions for workspace files
- Sets up Java and Gradle configurations
- Adds recommended VSCode extensions
- Configures debugging settings and launch configurations
- Sets up log watchers and GitHub queries
- Creates task definitions for common operations

##### `mgsnake set_java` (aliases: `java`, `sj`, `setJava`)

Configures Java for your workspace:

- Detects installed Java versions
- Allows selection of specific Java version
- Updates workspace settings to use selected version
- Configures both VSCode and shell environment
- Sets up Java formatter settings

##### `mgsnake set_gradle` (aliases: `gradle`, `sg`, `setGradle`)

Manages Gradle configuration:

- Detects installed Gradle versions
- Allows selection of specific Gradle version
- Updates workspace settings to use selected version
- Configures both VSCode and shell environment

##### `mgsnake init_local_config` (aliases: `iload`, `ilc`, `initLocalConfig`)

Sets up local development configurations:

- Creates a local configuration file for developer-specific settings
- Configures shell-specific environment variables
- Allows custom function definitions

#### Git & Release Management

##### `mgsnake diff_tree` (aliases: `dt`, `tree`, `createDiffTree`)

Creates a visual diff tree of the current branch against master.

- **Usage**: `mgsnake diff_tree [OPTIONS]`
- **Options**:
  - `-c, --commit-hash <hash>`: Compare against a specific commit instead of master.
  - `-d, --delete-original-files`: Delete generated copy of original files in the tree.
- **Output**: Generates a tree structure in `workspace_temp/diff_tree/` and opens it in VSCode.

##### `mgsnake remote_branches_details` (aliases: `rbd`, `remoteBranchesDetails`)

Generates a detailed report of remote branches.

- **Usage**: `mgsnake remote_branches_details [OPTIONS]`
- **Options**:
  - `-f, --filter-by <A|M|U>`: Filter by (A)ll, (M)erged, or (U)nmerged status against master.
- **Output**: Creates `workspace_temp/remote_branches.txt` with branch details (author, date, etc.).

##### `mgsnake remote_branches_cleanup` (aliases: `rbc`, `remoteBranchesCleanUp`)

Interactive tool to clean up merged remote branches.

- Parses the output of `remote_branches_details`
- Interactively asks which merged branches to delete from the remote
- Prunes local references

##### `mgsnake create_release` (aliases: `release`, `cr`, `createRelease`)

Creates a GitHub release and tag for the project.

- **Usage**: `mgsnake create_release <tag_suffix> <release_type> [notes] [branch]`
- **Arguments**:
  - `tag_suffix`: Suffix for the new tag.
  - `release_type`: `p` (Pre-release), `l` (Latest), `r` (Replace latest/Release).
  - `notes`: (Optional) Release notes.
  - `branch`: (Optional) Branch to create release from (defaults to current).

#### Utilities

##### `mgsnake graphql_schema` (aliases: `graphql`, `gql`, `cgs`, `createGraphqlSchema`)

Compiles GraphQL schema files.

- **Usage**: `mgsnake graphql_schema <schema_path>`
- Combines all schema files in the given directory into a single `.graphql` file and a `.json` introspection file.

##### `mgsnake expired_certs_jks` (aliases: `ecj`, `expiredCertsJks`)

Checks a Java KeyStore (JKS) for expired certificates.

- **Usage**: `mgsnake expired_certs_jks <jks_path> [-p password]`
- Lists aliases and valid dates, creating warnings for expired certs.

##### `mgsnake msg`

Internal utility to print and log formatted messages.

- **Usage**: `mgsnake msg <message> [-t type]`
- **Types**: `S` (Success), `I` (Info), `W` (Warning), `E` (Error), `T` (Tip).
