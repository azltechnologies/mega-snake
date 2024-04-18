setup_env(){
    WS_TEMP="./workspace_temp"
    if [ ! -z "$VER_GRADLE" ]; then
        source /Users/carlosmorales/IdeaProjects/stuff/gradleSet.sh
        set_gradle $VER_GRADLE
    fi

    if [ ! -z "$VER_JAVA" ]; then
        source /Users/carlosmorales/IdeaProjects/stuff/javaSet.sh
        set_java $VER_JAVA
    fi

    if [ "$CHECK_GCLOUD" = "true" ]; then
        source /Users/carlosmorales/IdeaProjects/stuff/gcloudSet.sh
        setCloud
    fi

    if [ "$UNTRACK_PROPS" = "true" ]; then
        source /Users/carlosmorales/IdeaProjects/stuff/untrackGradleProps.sh
        untrackProperties
    fi
    source /Users/carlosmorales/IdeaProjects/stuff/branchDetails.sh
}
echo "use the setup_env to start working on a repository"