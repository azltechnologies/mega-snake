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
