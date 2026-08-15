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
      mgsnake working-env

      # Check GraphQL schema
      mgsnake graphql-schema

      # Show branch details with debug info
      mgsnake --log-level DEBUG remote-branches-details
      ```

   > **Note**: Each command has its own help. Use `mgsnake <command> --help` for specific details.

### Prefer command aliases for daily use

Many command names are intentionally descriptive. For faster terminal workflows, use the aliases shown next to each command in [COMMANDS.md](COMMANDS.md).

```bash
# Full command
mgsnake working-env

# Alias
mgsnake cwe
```

## Available Commands

[See COMMANDS.md for the full list of available commands and their usage.](COMMANDS.md)

## Automated dependency vulnerability scanning

This repository combines two free, open-source tools to keep dependencies up to date and flag vulnerabilities:

- **[Dependabot](https://docs.github.com/en/code-security/dependabot)** (`.github/dependabot.yml`): opens weekly pull
  requests to update outdated `pip`/`uv` dependencies and GitHub Actions.
- **[`mgsnake scan-dependencies`](COMMANDS.md#scan-dependencies)**: audits the locked dependencies and files a GitHub
  issue for every new vulnerability finding. Any repo can reuse this by consuming `mgsnake`, regardless of its stack.

The scheduled/PR workflow that runs `mgsnake scan-dependencies` in CI lives at
[`.github/workflows/dependency-scan.yml`](.github/workflows/dependency-scan.yml). It runs weekly, on pull requests that
touch `pyproject.toml`/`uv.lock`, and on demand via `workflow_dispatch`. Consuming repos on other ecosystems should
adapt this workflow to install the right auditor (e.g. `osv-scanner`) and pass `--ecosystem` if auto-detection isn't
sufficient; `.github/dependabot.yml` and the workflow itself are inherently per-repo (GitHub reads them from the repo
where they live) and cannot be consumed remotely from the `mega-snake` package.
