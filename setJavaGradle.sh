set_args() {
    java -version
    #export JAVA_HOME=`/usr/libexec/java_home -v 17`
    source /Users/carlosmorales/IdeaProjects/stuff/gradleSet.sh $1
    local PARAM_JAVA=$2
    #local PARAM_JAVA=17
    echo "desired java version $PARAM_JAVA"
    local JAVA_VERSION=$(java -version  2>&1 | grep -oE '"[0-9\.\_]+\"' | grep -oE '[0-9\.\_]+' )
    echo "current java version: $JAVA_VERSION"
   
    text=$(/usr/libexec/java_home -V 2>&1)
    VERSIONS_JAVA=$(echo "$text" | /Users/carlosmorales/IdeaProjects/stuff/parse_java_versions.py)
    echo "$VERSIONS_JAVA"
    local VERSIONS_JAVA=("${(f)VERSIONS_JAVA}")
    declare -A JAVA_MAP
    local JAVA_KEYS=()
    for version in "${VERSIONS_JAVA[@]}"; do
        local key=$(echo $version | grep -oE '[0-9\._]+\:' | grep -oE '[0-9\._]+' || true)
        local value=$(echo $version | grep -oE ':.+$' | grep -oE '[^:].+$' || true)
        JAVA_MAP[$key]="$value"
        JAVA_KEYS+=("$key")
    done
        for key in "${(@k)JAVA_MAP}"; do
           echo "$key:${JAVA_MAP[$key]}"
        done
    JAVA_KEYS="${(j:\n:)JAVA_KEYS}"
    local JAVA_MATCHES=$(echo "$JAVA_KEYS" | grep -cE "^$PARAM_JAVA" || true)
    echo "a:$JAVA_MATCHES"
    if [ "$JAVA_MATCHES" -gt 1 ]; then
        echo "before"
        local JAVA_MATCHES=$(echo "$JAVA_KEYS" | grep -cE "^$PARAM_JAVA$" || true)
        echo "b:$JAVA_MATCHES"
        echo "after"
        if [ "$JAVA_MATCHES" -ne 1 ]; then
            echo "multiple available versions match with $PARAM_JAVA, please be more specific"
            return 1
        fi
        local JAVA_NEW=$JAVA_MAP[$PARAM_JAVA]
        export JAVA_HOME="$JAVA_NEW"
        echo "$JAVA_NEW"
    elif [ "$JAVA_MATCHES" -lt 1 ]; then
        echo "no java version found that matches with $PARAM_JAVA, please verify the desired java version"
        return 1
    else
        local JAVA_NEW=$(echo "$JAVA_KEYS" | grep -oE "^$PARAM_JAVA" || true)
        export JAVA_HOME=`/usr/libexec/java_home -v $JAVA_NEW`

    fi

    local IS_JAVA_SET=$(echo $JAVA_VERSION | grep -cE "^$JAVA_NEW" || true)

    if [ "$IS_JAVA_SET" -gt 0 ]; then
        echo "java version already set"
    else
        local JAVA_VERSION=$(java -version  2>&1 | grep -oE '"[0-9\.\_]+\"' | grep -oE '[0-9\.\_]+' )
        echo "Now using java version: $JAVA_VERSION"
    fi
}
