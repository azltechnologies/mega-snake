# Sets MEGA_SNAKE_SHELL for the current PowerShell session.
# Defines `mgsnake` as a thin wrapper around the real executable, so the commands whose work has to
# happen in this session can be acted on: a child process cannot mutate its parent's environment,
# so `mgsnake reload-config` and `mgsnake load-env` report what they need through their exit status
# and the wrapper below performs it here.
#
# The helpers are private (`__mgsnake_*`). The public interface is the CLI itself:
#     mgsnake reload-config      re-sources the local config file
#     mgsnake load-env [FILE]    exports the variables declared in an env file
# Both are documented like any other command (`mgsnake <command> --help`).

$env:MEGA_SNAKE_SHELL = "powershell"

# Exit statuses asking this session to act, mirroring RELOAD_ENVIRONMENT_EXIT_CODE and
# LOAD_ENV_EXIT_CODE in mega_snake/constants.py. `reload-config` needs no name here because it takes
# no arguments; only `load-env` has to be located in the arguments. A test fails if any of these
# three stops matching its Python counterpart.
$global:MegaSnakeReloadExitCode = 29
$global:MegaSnakeLoadEnvExitCode = 30
$global:MegaSnakeLoadEnvCommand = "load-env"

# Resolved once, and filtered to -CommandType Application on purpose: the function defined below
# shadows the executable by name, so this is what keeps the wrapper from calling itself.
$global:MegaSnakeExe = (Get-Command mgsnake -CommandType Application -ErrorAction SilentlyContinue |
    Select-Object -First 1).Source

function __mgsnake_reload {

    $local_config_file = & $global:MegaSnakeExe local-config-path
    if ($local_config_file -and (Test-Path -LiteralPath $local_config_file -PathType Leaf)) {
        & $global:MegaSnakeExe msg -t t -p "Loading config from " " $local_config_file"
        . $local_config_file
    }
    else {
        & $global:MegaSnakeExe msg -t w  "No local config file found"
    }
}

function __mgsnake_load_env {
    param(
        [string]$Path
    )
    $localEnvFile = & $global:MegaSnakeExe local-env-path

    if ($localEnvFile -and (Test-Path -LiteralPath $localEnvFile -PathType Leaf)) {
        $tmpEnvFile = $localEnvFile
    }
    else {
        $tmpEnvFile = ".env"
    }

    $envFile = if ($Path) { $Path } else { $tmpEnvFile }

    if (!(Test-Path -LiteralPath $envFile -PathType Leaf)) {
        return
    }

    Get-Content -LiteralPath $envFile | ForEach-Object {
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
    & $global:MegaSnakeExe msg -t t -p "Loading env variables from " "$envFile"
}

# Returns the single argument that follows the given command name, or "" when there is none. This is
# what lets `mgsnake --log-level DEBUG load-env foo.env` forward `foo.env` alone: forwarding the raw
# argument list would hand the global options to the helper, and parsing them here would mean
# reimplementing click in PowerShell. The command is looked up by its registered name, which is also
# why these two commands are registered without aliases.
#
# Returning a string rather than an array is deliberate. PowerShell unwraps a single-element array on
# return, so an array-shaped result turned into a bare string at the call site and `$result[0]` then
# indexed into it, yielding its first *character* -- `f` instead of `foo.env`. `load-env` takes at
# most one argument, so returning that one value has no such failure mode.
function __mgsnake_args_after {
    param(
        [string]$Wanted,
        [string[]]$Arguments
    )
    $index = [Array]::IndexOf($Arguments, $Wanted)
    if ($index -lt 0 -or $index -eq ($Arguments.Length - 1)) { return "" }
    return [string]$Arguments[$index + 1]
}

# The wrapper is the consumer of the signals. Without it the status is emitted and nothing ever
# captures it, which is exactly how the auto-reload stopped working when `mgsnake` became an
# installed executable invoked directly instead of through a shell function.
# $LASTEXITCODE is set explicitly at the end because the helpers run their own commands and would
# otherwise overwrite the status the caller is about to read.
#
# A dispatched signal is reported as success. The signal is a *request*, and once this function has
# carried it out the request is fulfilled -- there is nothing left to tell the caller. Propagating it
# would make every environment command look like a failure to any `if ($LASTEXITCODE -ne 0)` check.
# Every other status is passed through untouched.
function mgsnake {
    & $global:MegaSnakeExe @args
    $exitCode = $LASTEXITCODE
    # Reported to the caller; reset to 0 by whichever branch serves the request.
    $callerCode = $exitCode
    switch ($exitCode) {
        $global:MegaSnakeReloadExitCode {
            __mgsnake_reload
            $callerCode = 0
        }
        $global:MegaSnakeLoadEnvExitCode {
            $envFile = __mgsnake_args_after -Wanted $global:MegaSnakeLoadEnvCommand -Arguments $args
            if ($envFile) { __mgsnake_load_env -Path $envFile } else { __mgsnake_load_env }
            $callerCode = 0
        }
    }
    $global:LASTEXITCODE = $callerCode
}

__mgsnake_reload
__mgsnake_load_env