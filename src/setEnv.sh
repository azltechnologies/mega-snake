set_env() {
    PROP_FILE="$WS_CONFIG_HOME/config.properties"

    export WS_TEMP=$(grep "working_path" "$PROP_FILE" | sed 's/working_path=//')
    RE_PY_ENV=$(grep "python_virtual_bash" "$PROP_FILE" | sed 's/python_virtual_bash=//')
    PY_MODULE=$(grep "python_module" "$PROP_FILE" | sed 's/python_module=//')
    PYTHON_ENV="$WS_CONFIG_HOME/$RE_PY_ENV"
    source "$PYTHON_ENV"
    export PYTHONPATH="$WS_CONFIG_HOME"
    python3 -m $PY_MODULE "$@"
    deactivate
}
ws_tip "set_env" "use python version"
