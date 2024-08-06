    WS_CONFIG_HOME="$(readlink -f $(dirname "$0"))"
    source $WS_CONFIG_HOME/src/formatting.sh
setup_env(){
    WS_TEMP="./workspace_temp"
    source $WS_CONFIG_HOME/src/preloadConfig.sh
    if [ ! -z "$VER_GRADLE" ]; then
        source $WS_CONFIG_HOME/src/gradleSet.sh
        set_gradle $VER_GRADLE
    fi

    if [ ! -z "$VER_JAVA" ]; then
        source $WS_CONFIG_HOME/src/javaSet.sh
        set_java $VER_JAVA
    fi

    if [ ! -z "$CHECK_GCLOUD" ] && [ "$CHECK_GCLOUD" = "true" ]; then
        source $WS_CONFIG_HOME/src/gcloudSet.sh
        setCloud
    fi

    if [ ! -z "$UNTRACK_PROPS" ] && [ "$UNTRACK_PROPS" = "true" ]; then
        source $WS_CONFIG_HOME/src/untrackGradleProps.sh
        untrackProperties
    fi
    REMOTE_BRANCHES_OUTPUT="$WS_TEMP/remote_branches.txt"
    source $WS_CONFIG_HOME/src/branchDetails.sh
    source $WS_CONFIG_HOME/src/branchCleanUp.sh
    source $WS_CONFIG_HOME/src/expiredCertsJks.sh
    parse_gcloud_logs(){
        $WS_CONFIG_HOME/src/parseJsonLogs.sh $WS_TEMP $WS_CONFIG_HOME
    }
    ws_advice "use the parse_gcloud_logs function to parse gcloud logs from the $JSON_FILE file"
}
ws_advice "use the setup_env to start working on a repository"
