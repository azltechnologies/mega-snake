# Sets CODENAME_SNAKE_SHELL for the current shell session.
# Defines `snake_reload` to source the local configuration file (if present).
# Prints basic usage hints for `snake` and `snake_reload`.

if [ -n "${BASH_VERSION:-}" ]; then
    # Para bash
    CODENAME_SNAKE_SHELL="bash"
else
    # Para zsh
    CODENAME_SNAKE_SHELL="zsh"
fi
export CODENAME_SNAKE_SHELL
snake_reload() {
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
snake_reload
snake msg -t t -p "snake_reload" ": use this function to reload the local config file"
