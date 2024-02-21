set_args() {
    source /Users/carlosmorales/IdeaProjects/stuff/gradleSet.sh $1
    source /Users/carlosmorales/IdeaProjects/stuff/javaSet.sh $2
}

if [ ! -z "$VER_GRADLE" ] && [ ! -z "$VER_JAVA" ]; then
    set_args $VER_GRADLE $VER_JAVA
fi

if [ "$CHECK_GCLOUD" = "true" ]; then
    $IS_LOGGED=$(gcloud auth print-access-token | grep -cE 'Reauthentication required' || true)
    if [ "$IS_LOGGED" -eq 0 ]; then
        gcloud auth application-default login
    fi
fi
