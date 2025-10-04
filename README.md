# CodeName  `Snake`

A CLI tool focused on simplifying Java development with VSCode by automating workspace configuration and providing essential development tools. Its primary goal is to help developers quickly set up a fully configured workspace for Java projects using Gradle, complete with debugging capabilities and recommended extensions.

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

### Core Commands

The following commands are essential for setting up your development workspace:

#### `snake createWorkingEnv` (aliases: `cwe`, `env`)

Sets up a complete VSCode workspace configuration for Java development:

- Creates/updates VSCode workspace file with recommended settings
- Configures git exclusions for workspace files
- Sets up Java and Gradle configurations
- Adds recommended VSCode extensions
- Configures debugging settings and launch configurations
- Sets up log watchers and GitHub queries
- Creates task definitions for common operations

#### `snake setJava` (alias: `java`)

Configures Java for your workspace:

- Detects installed Java versions
- Allows selection of specific Java version
- Updates workspace settings to use selected version
- Configures both VSCode and shell environment
- Sets up Java formatter settings
- Ensures consistent Java version across team

#### `snake setGradle` (alias: `gradle`)

Manages Gradle configuration:

- Detects installed Gradle versions
- Allows selection of specific Gradle version
- Updates workspace settings to use selected version
- Configures both VSCode and shell environment
- Ensures consistent Gradle version across team

#### `snake initLocalConfig` (alias: `iload`)

Sets up local development configurations:

- Creates a local configuration file for developer-specific settings
- Configures shell-specific environment variables
- Allows custom function definitions
- Provides template for common local configurations

### Additional Commands
