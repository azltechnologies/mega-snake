# CodeName `Snake`

A CLI tool designed to standardize and automate the local development lifecycle. While its core focus is simplifying **Java/Gradle development in VS Code** ensuring consistent environments across teams, it also serves as a productivity swiss-army knife with utilities for **Git operations**, **GitHub release management**, and **Google Cloud Platform** observability.

## Project Setup

### Verify your Python version (3.13)

      ```bash
         python --version
      ```

      If don't have the right one, you can [download it from here](https://www.python.org/downloads/)

### Check if Poetry is installed

      ```bash
         poetry --version
      ```

   If not, [install it here.](https://python-poetry.org/docs/#installation)

### Configure Poetry to create venv in the current project

      ```bash
            poetry config virtualenvs.in-project true
      ```

### While being in the root path of this repository, install dependencies

      ```sh
            poetry install
      ```

   > **Note**: Repeat this command once inside the virtual env if some dependencies failed to generate.

### Create (or update) .`vscode/settings.json` file by adding the properties _`python.binPath`_ and _`python.defaultInterpreterPath`_

for windows:

      ```json
            {
               "python.binPath": ".venv/Scripts",
               "python.defaultInterpreterPath": ".venv/Scripts/python.exe"
            }
      ```

for mac & linux:

      ```json
            {
               "python.binPath": ".venv/bin",
               "python.defaultInterpreterPath": ".venv/bin/python3.13"
            }
      ```

## Usage

### Terminal Support

   The `snake` CLI works on:

- Windows: PowerShell
- macOS/Linux: bash or zsh

### Initialize Environment

   According to your terminal:

   ```bash
   # For bash/zsh
   source config_setup.sh

   # For PowerShell
   . .\config_setup.ps1
   ```

### Basic Usage

      ```bash
      # Show help
      snake --help

      # Execute commands with specific log level
      snake --log-level DEBUG <command>
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
      snake createWorkingEnv

      # Check GraphQL schema
      snake createGraphqlSchema

      # Show branch details with debug info
      snake --log-level DEBUG remoteBranchesDetails
      ```

   > **Note**: Each command has its own help. Use `snake <command> --help` for specific details.

### Available Commands

#### Environment & Configuration

##### `snake createWorkingEnv` (aliases: `cwe`, `env`)

Sets up a complete VSCode workspace configuration for Java development:

- Creates/updates VSCode workspace file with recommended settings
- Configures git exclusions for workspace files
- Sets up Java and Gradle configurations
- Adds recommended VSCode extensions
- Configures debugging settings and launch configurations
- Sets up log watchers and GitHub queries
- Creates task definitions for common operations

##### `snake setJava` (alias: `java`)

Configures Java for your workspace:

- Detects installed Java versions
- Allows selection of specific Java version
- Updates workspace settings to use selected version
- Configures both VSCode and shell environment
- Sets up Java formatter settings

##### `snake setGradle` (alias: `gradle`)

Manages Gradle configuration:

- Detects installed Gradle versions
- Allows selection of specific Gradle version
- Updates workspace settings to use selected version
- Configures both VSCode and shell environment

##### `snake initLocalConfig` (alias: `iload`)

Sets up local development configurations:

- Creates a local configuration file for developer-specific settings
- Configures shell-specific environment variables
- Allows custom function definitions

#### Git & Release Management

##### `snake createDiffTree` (aliases: `dt`, `tree`)

Creates a visual diff tree of the current branch against master.

- **Usage**: `snake createDiffTree [OPTIONS]`
- **Options**:
  - `-c, --commit-hash <hash>`: Compare against a specific commit instead of master.
  - `-d, --delete-original-files`: Delete generated copy of original files in the tree.
- **Output**: Generates a tree structure in `workspace_temp/diff_tree/` and opens it in VSCode.

##### `snake remoteBranchesDetails`

Generates a detailed report of remote branches.

- **Usage**: `snake remoteBranchesDetails [OPTIONS]`
- **Options**:
  - `-f, --filter-by <A|M|U>`: Filter by (A)ll, (M)erged, or (U)nmerged status against master.
- **Output**: Creates `workspace_temp/remote_branches.txt` with branch details (author, date, etc.).

##### `snake remoteBranchesCleanUp`

Interactive tool to clean up merged remote branches.

- Parses the output of `remoteBranchesDetails`
- Interactively asks which merged branches to delete from the remote
- Prunes local references

##### `snake createRelease`

Creates a GitHub release and tag for the project.

- **Usage**: `snake createRelease <tag_suffix> <release_type> [notes] [branch]`
- **Arguments**:
  - `tag_suffix`: Suffix for the new tag.
  - `release_type`: `p` (Pre-release), `l` (Latest), `r` (Replace latest/Release).
  - `notes`: (Optional) Release notes.
  - `branch`: (Optional) Branch to create release from (defaults to current).

#### Cloud & Logging (GCP)

##### `snake gcloudLogin` (alias: `gl`)

Logs into Google Cloud SDK.

- **Usage**: `snake gcloudLogin [OPTIONS]`
- **Options**:
  - `type-login`: Login type. `A` (Application Default), `U` (User), `B` (Both). Default is `B`.
  - `project`: (Optional) Project ID to set.

##### `snake gcloudLogout` (alias: `lg`)

Logs out of Google Cloud SDK and revokes credentials for both user and application default.

##### `snake bqInstancesQuery`

Generates a BigQuery-compatible query to filter logs by instance ID.

- **Usage**: `snake bqInstancesQuery <project> <deployment_id>...`
- Filters instances by deployment ID labels and copies the query to clipboard.

##### `snake parseJsonLogs`

Parses and formats JSON log files.

- **Usage**: `snake parseJsonLogs`
- Reads JSON logs from `workspace_temp/logs/parsed/*.json` and converts them to readable `.log` files in the same directory.

#### Utilities

##### `snake createGraphqlSchema` (aliases: `graphql`, `gql`)

Compiles GraphQL schema files.

- **Usage**: `snake createGraphqlSchema <schema_path>`
- Combines all schema files in the given directory into a single `.graphql` file and a `.json` introspection file.

##### `snake expiredCertsJks`

Checks a Java KeyStore (JKS) for expired certificates.

- **Usage**: `snake expiredCertsJks <jks_path> [-p password]`
- Lists aliases and valid dates, creating warnings for expired certs.

##### `snake msg`

Internal utility to print and log formatted messages.

- **Usage**: `snake msg <message> [-t type]`
- **Types**: `S` (Success), `I` (Info), `W` (Warning), `E` (Error), `T` (Tip).
