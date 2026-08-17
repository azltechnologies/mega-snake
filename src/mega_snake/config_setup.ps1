# Sets MEGA_SNAKE_SHELL for the current PowerShell session.
# Defines `mgsnake` as a thin wrapper around the real executable, so the auto-reload signal
# (exit status 29) can be acted on: a child process cannot mutate its parent's environment,
# so re-sourcing the local environment files has to happen here, in the user's own session.
# Defines `mgsnake_reload`, `mgsnake_load_env` and `mgsnake_reload_all`.

$env:MEGA_SNAKE_SHELL = "powershell"

# Exit status meaning "success, and the shell must re-source its local environment files".
# Mirrors RELOAD_ENVIRONMENT_EXIT_CODE in mega_snake/constants.py; the two have to agree.
$global:MegaSnakeReloadExitCode = 29

# Resolved once, and filtered to -CommandType Application on purpose: the function defined below
# shadows the executable by name, so this is what keeps the wrapper from calling itself.
$global:MegaSnakeExe = (Get-Command mgsnake -CommandType Application -ErrorAction SilentlyContinue |
    Select-Object -First 1).Source

function mgsnake_reload {

    $local_config_file = & $global:MegaSnakeExe get-local-config-path
    if (Test-Path $local_config_file) {
        & $global:MegaSnakeExe msg -t i "Reloading $local_config_file"
        . $local_config_file
    }
    else {
        & $global:MegaSnakeExe msg -t w  "No local config file found"
    }
}

function mgsnake_load_env {
    param(
        [string]$Path = ".env"
    )
    if (!(Test-Path $Path)) { return }

    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()

        # Ignorar líneas vacías y comentarios
        if ($line -and !$line.StartsWith('#') -and $line -match '^([^=]+)=(.*)$') {
            $key = $Matches[1].Trim()

            # Remover comillas externas (simples o dobles) si existen
            $value = $Matches[2].Trim() -replace '^["'']|["'']$'

            # Asignar a las variables de entorno del proceso actual
            [Environment]::SetEnvironmentVariable($key, $value, 'Process')
        }
    }
    & $global:MegaSnakeExe msg -t t -p "mgsnake_load_env" ": Environment variables loaded from $Path"
}

# Reloads both local environment files in one step. This is what the wrapper calls, so a command
# that rewrites either of them takes effect in the current session without opening a new terminal.
function mgsnake_reload_all {
    mgsnake_reload
    mgsnake_load_env
}

# The wrapper is the consumer of the reload signal. Without it the status is emitted and nothing
# ever captures it, which is exactly how the auto-reload stopped working when `mgsnake` became an
# installed executable invoked directly instead of through a shell function.
# $LASTEXITCODE is restored at the end because mgsnake_reload_all runs its own commands and would
# otherwise overwrite the status the caller is about to read.
function mgsnake {
    & $global:MegaSnakeExe @args
    $exitCode = $LASTEXITCODE
    if ($exitCode -eq $global:MegaSnakeReloadExitCode) {
        mgsnake_reload_all
    }
    $global:LASTEXITCODE = $exitCode
}

& $global:MegaSnakeExe msg -t t -p "mgsnake" ": use this function to set the environment configuration"
mgsnake_reload
& $global:MegaSnakeExe msg -t t -p "mgsnake_reload" ": use this function to reload the local config file"
& $global:MegaSnakeExe msg -t t -p "mgsnake_reload_all" ": reloads the local config file and the .env file"
