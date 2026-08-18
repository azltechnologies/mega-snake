# Sets MEGA_SNAKE_SHELL for the current shell session.
# Defines `mgsnake` as a thin wrapper around the real executable, so the commands whose work has to
# happen in this session can be acted on: a child process cannot mutate its parent's environment,
# so `mgsnake reload-config` and `mgsnake load-env` report what they need through their exit status
# and the wrapper below performs it here.
#
# The helpers are private (`__mgsnake_*`). The public interface is the CLI itself:
#     mgsnake reload-config      re-sources the local config file
#     mgsnake load-env [FILE]    exports the variables declared in an env file
# Both are documented like any other command (`mgsnake <command> --help`).

if [ -n "${BASH_VERSION:-}" ]; then
    # Para bash
    MEGA_SNAKE_SHELL="bash"
else
    # Para zsh
    MEGA_SNAKE_SHELL="zsh"
fi
export MEGA_SNAKE_SHELL

# Exit statuses asking this shell to act, mirroring RELOAD_ENVIRONMENT_EXIT_CODE and
# LOAD_ENV_EXIT_CODE in mega_snake/constants.py. `reload-config` needs no name here because it takes
# no arguments; only `load-env` has to be located in "$@". A test fails if any of these three stops
# matching its Python counterpart.
MEGA_SNAKE_RELOAD_EXIT_CODE=29
MEGA_SNAKE_LOAD_ENV_EXIT_CODE=30
MEGA_SNAKE_LOAD_ENV_COMMAND="load-env"

__mgsnake_reload() {
    local local_config_file
    # `command` reaches the real executable, never this file's function, so the helpers can never
    # recurse into the wrapper below.
    local_config_file=$(command mgsnake local-config-path)

    if [ -f "$local_config_file" ]; then
        command mgsnake msg -t t -p "Loading config from " "$local_config_file"
        # shellcheck source=/dev/null
        source "$local_config_file"
    else
        command mgsnake msg -t w "No local config file found"
    fi
}

__mgsnake_load_env() {
    local env_file="$1"

    if [[ -z "$env_file" ]]; then
        local local_env_file
        local_env_file=$(command mgsnake local-env-path)
        [[ -f "$local_env_file" ]] && env_file="$local_env_file" || env_file=.env
    fi
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
    done <"$env_file"
    command mgsnake msg -t t -p "Loading env variables from " "$env_file"
}

# Drops everything up to and including the given command name, leaving that command's own arguments
# in "$@". This is what lets `mgsnake --log-level DEBUG load-env foo.env` forward `foo.env` alone:
# forwarding the raw "$@" would hand the global options to the helper, and parsing them here would
# mean reimplementing click in shell. The command is looked up by its registered name, which is also
# why these two commands are registered without aliases.
__mgsnake_args_after() {
    local wanted="$1"
    shift
    while [ $# -gt 0 ]; do
        if [ "$1" = "$wanted" ]; then
            shift
            printf '%s\n' "$@"
            return 0
        fi
        shift
    done
}

# The wrapper is the consumer of the signals. Without it the status is emitted and nothing ever
# captures $?, which is exactly how the auto-reload stopped working when `mgsnake` became an
# installed executable invoked directly instead of through a shell function.
# `type mgsnake` reporting a function is the only visible difference.
#
# A dispatched signal is reported as success. The signal is a *request*, and once this function has
# carried it out the request is fulfilled -- there is nothing left to tell the caller. Propagating it
# would make every environment command look like a failure: `mgsnake set-java && echo ok` would never
# print, and a `set -e` script would abort on the happy path of `mgsnake load-env`. Every other
# status is passed through untouched.
mgsnake() {
    command mgsnake "$@"
    local exit_code=$?
    case "$exit_code" in
    "$MEGA_SNAKE_RELOAD_EXIT_CODE")
        __mgsnake_reload
        return 0
        ;;
    "$MEGA_SNAKE_LOAD_ENV_EXIT_CODE")
        local env_file
        env_file=$(__mgsnake_args_after "$MEGA_SNAKE_LOAD_ENV_COMMAND" "$@")
        __mgsnake_load_env "$env_file"
        return 0
        ;;
    esac
    return "$exit_code"
}

__mgsnake_reload
# Explicit on purpose: an empty argument here would fall back to whatever `.env` happens to sit in
# the directory this terminal opened in. Naming the local environment file removes that exposure --
# see the "no-argument auto-load" note in .github/copilot-instructions.md §7.4.
__mgsnake_load_env "$(command mgsnake local-env-path)"
