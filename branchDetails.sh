remoteBranchesDetails(){
    {
      function printingRemoteBranchesDetails(){
            local PADDING=20
            local PADDING_AUTH=35
            local PADDING_BRANCH=50
            local DELIMITER=" | "
            printf "%-${PADDING}s${DELIMITER}%-${PADDING}s${DELIMITER}%-${PADDING_AUTH}s${DELIMITER}%-${PADDING_BRANCH}s${DELIMITER}%-${PADDING}s\n" "$1" "$2" "$3" "$4" "$5"
        }

        declare -A BRANCHES_MAP
        local BRANCHES_KEYS=()
        local HEAD="remotes/origin/HEAD"
        for BRANCH in $(git branch -a  | grep -Eo 'remotes/\S+' || true); do
            if [ "$BRANCH" != "$HEAD" ]; then
                local LAST_COMMIT=$(git log -1 "$BRANCH")
                local ID_COMMIT=$(echo "$LAST_COMMIT" | grep -Eo 'commit\s+\w+' | grep -oE '\w+$' || true)
                local TIME_COMMIT=$(git log -1 $BRANCH --pretty="format:%at")
                local TIME_STRING=$(gdate -d "@${TIME_COMMIT}" +%FT%TZ)
                local AUTHOR_COMMIT=$(git log -1 $BRANCH --pretty="format:%ae")
                local MESSAGE_COMMIT=$(git log -1 $BRANCH --pretty="format:%B")
                local MESSAGE_COMMIT=${MESSAGE_COMMIT//$'\n'/$'\t'}
                local MESSAGE_COMMIT=${MESSAGE_COMMIT//$'\r'/$'\t'}
                local LOCAL_BRANCH=${BRANCH#remotes/origin/}
                #printf "%-${PADDING}s${DELIMITER}%-${PADDING}s${DELIMITER}%-${PADDING_AUTH}s${DELIMITER}%-${PADDING}s\n" "$ID_COMMIT1" "$TIME_STRING" "$AUTHOR_COMMIT" "$MESSAGE_COMMIT"
                #BRANCHES_MAP[TIME_COMMIT]=$(printing "$ID_COMMIT" "$TIME_STRING" "$AUTHOR_COMMIT" "$MESSAGE_COMMIT")
                BRANCHES_MAP[$TIME_COMMIT]=$(printingRemoteBranchesDetails "$ID_COMMIT" "$TIME_STRING" "$AUTHOR_COMMIT" "$LOCAL_BRANCH" "$MESSAGE_COMMIT")
                BRANCHES_KEYS+=("$TIME_COMMIT")
            fi
        done
        local SORTED_BRANCHES=$(echo "${BRANCHES_KEYS[@]}" | /Users/carlosmorales/IdeaProjects/stuff/sort_numbers.py)
        local SORTED_BRANCHES=("${(f)SORTED_BRANCHES}")
        local OUTPUT="$WS_TEMP/remote_branches.txt"
        rm $OUTPUT
        # Print the sorted array
        for branch in "${SORTED_BRANCHES[@]}"; do
            echo "$BRANCHES_MAP[$branch]" >> "$OUTPUT"
        done
        code "$OUTPUT"
    } always {
        unfunction -m "printingRemoteBranchesDetails"
    }
}