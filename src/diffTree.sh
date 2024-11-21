set_env() {
    source "$WS_CONFIG_HOME/.venv/bin/activate"
    export PYTHONPATH="$WS_CONFIG_HOME"
    python3 -m py "$@"
    deactivate
}
ws_tip "set_env" "use python version"
