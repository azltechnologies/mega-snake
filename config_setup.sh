    WS_CONFIG_HOME="$(readlink -f $(dirname "$0"))"
    source $WS_CONFIG_HOME/formatting.sh
setup_env(){
    WS_TEMP="./workspace_temp"
    source $WS_CONFIG_HOME/preloadConfig.sh
    if [ ! -z "$VER_GRADLE" ]; then
        source $WS_CONFIG_HOME/gradleSet.sh
        set_gradle $VER_GRADLE
    fi

    if [ ! -z "$VER_JAVA" ]; then
        source $WS_CONFIG_HOME/javaSet.sh
        set_java $VER_JAVA
    fi

    if [ ! -z "$CHECK_GCLOUD" ] && [ "$CHECK_GCLOUD" = "true" ]; then
        source $WS_CONFIG_HOME/gcloudSet.sh
        setCloud
    fi

    if [ ! -z "$UNTRACK_PROPS" ] && [ "$UNTRACK_PROPS" = "true" ]; then
        source $WS_CONFIG_HOME/untrackGradleProps.sh
        untrackProperties
    fi
    REMOTE_BRANCHES_OUTPUT="$WS_TEMP/remote_branches.txt"
    source $WS_CONFIG_HOME/branchDetails.sh
    source $WS_CONFIG_HOME/branchCleanUp.sh
}
ws_advice "use the setup_env to start working on a repository"
