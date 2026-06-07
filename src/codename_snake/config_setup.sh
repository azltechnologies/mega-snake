# Detects if  the script is being run in bash or zsh and sets the appropriate configuration directory and shell type.
# It also defines a function `l_reload` to reload the local configuration file and a function `snake` to execute
# a Python module with the correct environment. Finally, it provides some user messages about how to use these functions.

if [ -n "${BASH_VERSION:-}" ]; then
    # Para bash
    CODENAME_SNAKE_SHELL="bash"
else
    # Para zsh
    CODENAME_SNAKE_SHELL="zsh"
fi
export CODENAME_SNAKE_SHELL
l_reload() {
    local local_config_file
    local_config_file=$(snake get-local-config-path)

    if [ -f "$local_config_file" ]; then
        snake msg -t i "Reloading $local_config_file"
        # shellcheck source=/dev/null
        source "$local_config_file"
    else
        snake msg -t w "No local config file found"
    fi
}

snake msg -t t -p "snake" ": use this function to set the environment configuration"
l_reload
snake msg -t t -p "l_reload" ": use this function to reload the local config file"
