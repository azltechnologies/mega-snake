# Sets CODENAME_SNAKE_SHELL for the current PowerShell session.
# Defines `l_reload` to dot-source the local configuration file (if present).
# Prints basic usage hints for `snake` and `l_reload`.

$env:CODENAME_SNAKE_SHELL = "powershell"

function l_reload {

    $local_config_file = snake get-local-config-path
    if (Test-Path $local_config_file) {
        snake msg -t i "Reloading $local_config_file"
        . $local_config_file
    }
    else {
        snake msg -t w  "No local config file found"
    }
}
snake msg -t t -p "snake" ": use this function to set the environment configuration"
l_reload
snake msg -t t -p "l_reload" ": use this function to reload the local config file"