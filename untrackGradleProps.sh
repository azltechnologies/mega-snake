untrackProperties(){
    local PROP_FILE='gradle.properties'
    if [ -f "$PROP_FILE" ]; then
        local UNTRACKED=$(git ls-files -v | grep -Ec "H\s+$PROP_FILE")
        if [ "$UNTRACKED" -eq 1 ]; then
            echo "untracking $PROP_FILE"
            git update-index --assume-unchanged $PROP_FILE
        fi
    fi
}