# Sets MEGA_SNAKE_SHELL for the current shell session.
# Defines `mgsnake_reload` to source the local configuration file (if present).
# Prints basic usage hints for `mgsnake` and `mgsnake_reload`.

if [ -n "${BASH_VERSION:-}" ]; then
    # Para bash
    MEGA_SNAKE_SHELL="bash"
else
    # Para zsh
    MEGA_SNAKE_SHELL="zsh"
fi
export MEGA_SNAKE_SHELL
mgsnake_reload() {
    local local_config_file
    local_config_file=$(mgsnake get-local-config-path)

    if [ -f "$local_config_file" ]; then
        mgsnake msg -t i "Reloading $local_config_file"
        # shellcheck source=/dev/null
        source "$local_config_file"
    else
        mgsnake msg -t w "No local config file found"
    fi
}

mgsnake msg -t t -p "mgsnake" ": use this function to set the environment configuration"
mgsnake_reload
mgsnake msg -t t -p "mgsnake_reload" ": use this function to reload the local config file"
