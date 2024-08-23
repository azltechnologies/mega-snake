    WS_CONFIG_HOME="$(readlink -f $(dirname "$0"))"
    source $WS_CONFIG_HOME/src/formatting.sh
setup_env(){
    WS_TEMP="./workspace_temp"
    source $WS_CONFIG_HOME/src/preloadConfig.sh
    if [ -n "$1" ] && [ "$1" -gt 0 ]; then

        if [ ! -z "$UNTRACK_PROPS" ] && [ "$UNTRACK_PROPS" = "true" ] && [ "$1" -ge 1 ]; then
            source $WS_CONFIG_HOME/src/untrackGradleProps.sh
            untrackProperties
        fi
        if [ -n "$VER_GRADLE" ] && [ "$VER_GRADLE" != "false" ] && [ "$1" -ge 2 ]; then
            source $WS_CONFIG_HOME/src/gradleSet.sh
            set_gradle $VER_GRADLE
        fi

        if [ -n "$VER_JAVA" ] && [ "$VER_JAVA" != "false" ] && [ "$1" -ge 2 ]; then
            source $WS_CONFIG_HOME/src/javaSet.sh
            set_java $VER_JAVA
        fi

        if [ ! -z "$CHECK_GCLOUD" ] && [ "$CHECK_GCLOUD" = "true" ] && [ "$1" -ge 3 ]; then
            source $WS_CONFIG_HOME/src/gcloudSet.sh
            setCloud
        fi

    fi
    REMOTE_BRANCHES_OUTPUT="$WS_TEMP/remote_branches.txt"
    DIFF_TREE_OUTPUT="$WS_TEMP/diff_tree"
    source $WS_CONFIG_HOME/src/diffTree.sh
    source $WS_CONFIG_HOME/src/branchDetails.sh
    source $WS_CONFIG_HOME/src/branchCleanUp.sh
    source $WS_CONFIG_HOME/src/expiredCertsJks.sh
    create_release(){
        git fetch --all
        python3 $WS_CONFIG_HOME/py/create_release/create.py "$@"
    }
    ws_tip "create_release <tag_suffix> <release_type> <release_notes>" "create a release in the current repo"
    parse_gcloud_logs(){
        $WS_CONFIG_HOME/src/parseJsonLogs.sh $WS_TEMP $WS_CONFIG_HOME
    }
    ws_tip "parse_gcloud_logs" "parse gcloud logs in json format"
}
ws_tip "setup_env <level>" "start working on a repository and set up the environment
    setup_env <level>
    level: 0 - only set up the environment
    level: 1 - untrack gradle properties
    level: 2 - set gradle and java versions
    level: 3 - set gcloud configurations"
