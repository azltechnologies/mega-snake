set_args() {
    #export JAVA_HOME=`/usr/libexec/java_home -v 17`
    local PARAM_GRADLE=$1
    echo "desired gradle version $PARAM_GRADLE"
    local PARAM_JAVA=$2
    local PARAM_JAVA=17
    echo "desired java version $PARAM_JAVA"
    local TEMP=$(gradle -v 2>/dev/null | grep Gradle | grep -oE ' [0-9\.]+' | grep -oE '[0-9\.]+' || true)
    if [ ! -z "$TEMP" ]; then
        until [ ! -z "$GRADLE_VERSION" ]; do
            for FORMULA in $(brew list | grep gradle ); do
                if [ "$FORMULA" = "gradle" ]; then
                    local VER_FORMULA=8
                else
                    local VER_FORMULA=$(echo $FORMULA | grep -oE "@[0-9\.]+"| grep -oE "[0-9]+(\.[0-9]+)?")
                fi
                IS_GRADLE_VER=$(echo $TEMP | grep -cE "^$VER_FORMULA$" || true)
                if [ "$IS_GRADLE_VER" -gt 0 ]; then
                    local GRADLE_VERSION=$TEMP
                    break;
                fi
            done
            local TEMP=${TEMP%?}
        done
    fi
    echo "current gradle version: $GRADLE_VERSION"
    local JAVA_VERSION=$(java -version  2>&1 | grep -oE '"[0-9\.\_]+\"' | grep -oE '[0-9\.\_]+' )
    echo "current java version: $JAVA_VERSION"
    if [ -z "$PARAM_GRADLE" ] || [ -z "$PARAM_JAVA" ]; then
        echo "args not set"
        return 1
    fi
    local IS_GRADLE_SET=$(echo $GRADLE_VERSION | grep -cE "^$PARAM_GRADLE$" || true)

    if [ "$IS_GRADLE_SET" -gt 0 ]; then
        echo "gradle version already set"
    else

        declare -A GRADLE_MAP

        GRADLE_MAP["$(brew info gradle | grep -oE 'stable [0-9]*\.' | grep -oE ' [0-9]*\.' | grep -oE '[0-9]*')"]="gradle"
        for FORMULA in $(brew list | grep gradle@ ); do
            GRADLE_MAP["$(echo $FORMULA | grep -oE "@[0-9\.]+"| grep -oE "[0-9]+(\.[0-9]+)?")"]=$FORMULA
        done

        #for key in "${(@k)GRADLE_MAP}"; do
        #   echo "$key:${GRADLE_MAP[$key]}"
        #done
        if [ ! -z "$GRADLE_VERSION" ]; then
            echo "removing current gradle version ${GRADLE_MAP["$GRADLE_VERSION"]}"
            brew unlink ${GRADLE_MAP["$GRADLE_VERSION"]}
        fi

        brew link ${GRADLE_MAP["$PARAM_GRADLE"]}
        local GRADLE_VERSION=$(gradle -v 2>/dev/null | grep Gradle | grep -oE ' [0-9\.]+' | grep -oE '[0-9\.]+' || true)
        echo "Now using gradle version: $GRADLE_VERSION"
    fi

    text=$(/usr/libexec/java_home -V 2>&1)
local VERSIONS_JAVA=$(
python3 - <<END
import re

text = """$text"""
my_dictionary = {}
pattern = r"^.+\s\-\s\"[\w\s\.]+\"\s/.+$"
matches = re.findall(pattern, text, re.MULTILINE)
result = ''
for match in matches:
    ver_pattern = r"(?<=\s)/.+$"
    version = re.search(ver_pattern,match).group()
    key_pattern = r"^\s+[0-9\._]+"
    key = re.search(key_pattern,match).group()
    key_pattern = r"[0-9\._]+"
    key = re.search(key_pattern,match).group()
    print(key+':'+version.replace("\"",""))
    ##my_dictionary[key] = version.replace("\"","")
##print(my_dictionary)
END
)

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
