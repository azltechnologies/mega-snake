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

    if [ $exit_code -eq 1 ]; then
        l_reload
    fi

    return $exit_code
}
l_reload
set_env msg -t t "l_reload" ": use this function to reload the local config file"
setup_env() {
    export WS_TEMP="./workspace_temp"

    # Check if ./build.gradle exists and store the result in a variable
    GRADLE_FILE_EXISTS=$(ls | grep -cE 'build.gradle' || true)
    if [ "$GRADLE_FILE_EXISTS" -eq 1 ]; then
        source $WS_CONFIG_HOME/src/preloadConfig.sh
    fi

    if [ -n "$1" ] && [ "$1" -gt 0 ]; then

        if [ "$GRADLE_FILE_EXISTS" -eq 1 ] && [ "$1" -ge 1 ]; then
            source $WS_CONFIG_HOME/src/untrackGradleProps.sh
            untrackProperties
        fi
        if [ -n "$VER_GRADLE" ] && [[ "$VER_GRADLE" =~ ^[0-9]+(\.[0-9]+)*$ ]] && [ "$1" -ge 2 ]; then
            source $WS_CONFIG_HOME/src/gradleSet.sh
            set_gradle $VER_GRADLE
        fi

        if [ -n "$VER_JAVA" ] && [[ "$VER_JAVA" =~ ^[0-9]+(\.[0-9]+)*$ ]] && [ "$1" -ge 2 ]; then
            source $WS_CONFIG_HOME/src/javaSet.sh
            set_java $VER_JAVA
        fi

        if [ "$1" -ge 3 ]; then
            source $WS_CONFIG_HOME/src/gcloudSet.sh
            setCloud
        fi

    fi
    source $WS_CONFIG_HOME/src/expiredCertsJks.sh
}
ws_tip "setup_env <level>" "start working on a repository and set up the environment
    setup_env <level>
    level: 0 - only set up the environment
    level: 1 - untrack gradle properties
    level: 2 - set gradle and java versions
    level: 3 - set gcloud configurations"
