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

mgsnake_load_env() {
  local env_file="${1:-.env}"
  [[ -f "$env_file" ]] || return 1

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
  mgsnake msg -t t -p "mgsnake_load_env" ": Environment variables loaded from $env_file"
}

mgsnake msg -t t -p "mgsnake" ": use this function to set the environment configuration"
mgsnake_reload
mgsnake msg -t t -p "mgsnake_reload" ": use this function to reload the local config file"
