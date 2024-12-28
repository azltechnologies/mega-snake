# Detecta si está corriendo en bash o zsh y obtiene el directorio correcto
if [ -n "$BASH_SOURCE" ]; then
    # Para bash
    export WS_CONFIG_HOME="$(readlink -f $(dirname "${BASH_SOURCE[0]}"))"
    export WS_SHELL="bash"
else
    # Para zsh
    export WS_CONFIG_HOME="$(readlink -f $(dirname "$0"))"
    export WS_SHELL="zsh"
fi
source $WS_CONFIG_HOME/src/formatting.sh #ya
l_reload() {
    local PROP_FILE="$WS_CONFIG_HOME/config.properties"
    local LOCAL_CONFIG=$(grep "local_config_file_name" "$PROP_FILE" | sed 's/local_config_file_name=//')
    local WORKING_PATH=$(grep "working_path" "$PROP_FILE" | sed 's/working_path=//')
    local local_config_file="$PWD/$WORKING_PATH/$LOCAL_CONFIG.sh"
    if [ -f "$local_config_file" ]; then
        set_env msg -t i "Reloading $local_config_file"
        source $local_config_file
    else
        set_env msg -t w "No local config file found"
    fi
}
set_env() {
    local PROP_FILE="$WS_CONFIG_HOME/config.properties"

    local RE_PY_ENV=$(grep "python_virtual_bash" "$PROP_FILE" | sed 's/python_virtual_bash=//')
    local PY_MODULE=$(grep "python_module" "$PROP_FILE" | sed 's/python_module=//')
    local PYTHON_ENV="$WS_CONFIG_HOME/$RE_PY_ENV"
    source "$PYTHON_ENV"
    export PYTHONPATH="$WS_CONFIG_HOME"
    python3 -m $PY_MODULE --shell "$WS_SHELL" "$@"

    # catch exit code
    local exit_code=$?

    deactivate

    if [ $exit_code -eq 21 ]; then
        l_reload
    fi

    return $exit_code
}
l_reload
set_env msg -t t -p "l_reload" ": use this function to reload the local config file"
