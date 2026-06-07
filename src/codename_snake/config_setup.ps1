# Detects the current configuration directory and shell type.
# It also defines a function `l_reload` to reload the local configuration file and a function `snake` to execute
# a Python module with the correct environment. Finally, it provides some user messages about how to use these functions.

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