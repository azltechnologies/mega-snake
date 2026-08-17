# Sets MEGA_SNAKE_SHELL for the current shell session.
# Defines `mgsnake` as a thin wrapper around the real executable, so the auto-reload signal
# (exit status 29) can be acted on: a child process cannot mutate its parent's environment,
# so re-sourcing the local environment files has to happen here, in the user's own shell.
# Defines `mgsnake_reload`, `mgsnake_load_env` and `mgsnake_reload_all`.

if [ -n "${BASH_VERSION:-}" ]; then
    # Para bash
    MEGA_SNAKE_SHELL="bash"
else
    # Para zsh
    MEGA_SNAKE_SHELL="zsh"
fi
export MEGA_SNAKE_SHELL

# Exit status meaning "success, and the shell must re-source its local environment files".
# Mirrors RELOAD_ENVIRONMENT_EXIT_CODE in mega_snake/constants.py; the two have to agree.
MEGA_SNAKE_RELOAD_EXIT_CODE=29

mgsnake_reload() {
    local local_config_file
    # `command` reaches the real executable, never this file's function, so the helpers can never
    # recurse into the wrapper below.
    local_config_file=$(command mgsnake get-local-config-path)

    if [ -f "$local_config_file" ]; then
        command mgsnake msg -t i "Reloading $local_config_file"
        # shellcheck source=/dev/null
        source "$local_config_file"
    else
        command mgsnake msg -t w "No local config file found"
    fi
}

mgsnake_load_env() {
  local env_file="${1:-.env}"
  [[ -f "$env_file" ]] || return 0

  while IFS='=' read -r key value || [[ -n "$key" ]]; do
    # 1. Ignorar comentarios y líneas vacías
    [[ "$key" =~ ^[[:space:]]*# ]] || [[ -z "$key" ]] && continue

    # 2. Limpiar espacios en la clave
    key=$(echo "$key" | tr -d '[:space:]')

    # 3. Limpiar espacios y quitar comillas externas (simples o dobles) del valor
    value=$(echo "$value" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^["'\'']//' -e 's/["'\'']$//')

    # 4. Exportar de forma segura al entorno actual
    export "$key"="$value"
  done < "$env_file"
  command mgsnake msg -t t -p "mgsnake_load_env" ": Environment variables loaded from $env_file"
}

# Reloads both local environment files in one step. This is what the wrapper calls, so a command
# that rewrites either of them takes effect in the current session without opening a new terminal.
mgsnake_reload_all() {
    mgsnake_reload
    mgsnake_load_env
}

# The wrapper is the consumer of the reload signal. Without it the status is emitted and nothing
# ever captures $?, which is exactly how the auto-reload stopped working when `mgsnake` became an
# installed executable invoked directly instead of through a shell function.
# `type mgsnake` reporting a function is the only visible difference.
mgsnake() {
    command mgsnake "$@"
    local exit_code=$?
    if [ "$exit_code" -eq "$MEGA_SNAKE_RELOAD_EXIT_CODE" ]; then
        mgsnake_reload_all
    fi
    return "$exit_code"
}

command mgsnake msg -t t -p "mgsnake" ": use this function to set the environment configuration"
mgsnake_reload
command mgsnake msg -t t -p "mgsnake_reload" ": use this function to reload the local config file"
command mgsnake msg -t t -p "mgsnake_reload_all" ": reloads the local config file and the .env file"
