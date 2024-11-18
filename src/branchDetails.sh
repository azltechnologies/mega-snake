remoteBranchesDetails(){
    # Define the option string
    OPTSTRING="f"
    while getopts ${OPTSTRING} opt; do
        case $opt in
            f ) 
                local filter_flag="true"
            ;;
            \? )
                ws_warning "Invalid option: $OPTARG" 1>&2
                return 1
            ;;
            : )
                ws_warning "Option -$OPTARG requires an argument." 1>&2
                return 1
            ;;
        esac
    done

      printingRemoteBranchesDetails(){
            local PADDING=20
            local PADDING_AUTH=50
            local PADDING_BRANCH=50
            local DELIMITER=" | "
            printf "%3s${DELIMITER}%-${PADDING}s${DELIMITER}%-${PADDING}s${DELIMITER}%-${PADDING_AUTH}s${DELIMITER}%-${PADDING_BRANCH}s${DELIMITER}%-${PADDING}s${DELIMITER}%-${PADDING}s\n" "$1" "$2" "$3" "$4" "$5" "$6" "$7"
        }

        declare -A BRANCHES_MAP
        local BRANCHES_KEYS=()
        local HEAD="remotes/origin/HEAD"
        local MAIN_BRANCH=$(git remote show origin | sed -n '/HEAD branch/s/.*: //p')
        local BRANCHES_PENDING=$(git branch -a | grep -Eo 'remotes/\S+' | grep -vE $HEAD | wc -l |  awk '{$1=$1};1')
        ws_advice "main branch: $MAIN_BRANCH; branches to process: $BRANCHES_PENDING"
        for BRANCH in $(git branch -a  | grep -Eo 'remotes/\S+' | grep -vE $HEAD || true); do
            local LAST_COMMIT=$(git log -1 "$BRANCH")
            local ID_COMMIT=$(echo "$LAST_COMMIT" | grep -Eo 'commit\s+\w+' | grep -oE '\w+$' | head -n 1 || true)
            ws_info "branches pending: $BRANCHES_PENDING; processing branch in commit $ID_COMMIT"
            local MERGED=$(git branch --contains $ID_COMMIT | grep -cE "\b$MAIN_BRANCH$" || true)
            if [ "$filter_flag" != "true" ] || [ "$MERGED" -eq 1 ]; then
                local COMMON_ANCESTOR=$(git merge-base $MAIN_BRANCH $BRANCH)
                local TIME_COMMIT=$(git log -1 $BRANCH --pretty="format:%at")
                local TIME_STRING=$(gdate -d "@${TIME_COMMIT}" +%FT%TZ)
                local AUTHOR_COMMIT=$(git log -1 $BRANCH --pretty="format:%ae")
                local MESSAGE_COMMIT=$(git log -1 $BRANCH --pretty="format:%B")
                local MESSAGE_COMMIT=${MESSAGE_COMMIT//$'\n'/$'\t'}
                local MESSAGE_COMMIT=${MESSAGE_COMMIT//$'\r'/$'\t'}
                local LOCAL_BRANCH=${BRANCH#remotes/origin/}
                local DUPLICATES=$(echo $BRANCHES_KEYS | grep -o $TIME_COMMIT | wc -l |  awk '{$1=$1};1')
                local KEY_COMMIT=$(echo "$TIME_COMMIT + $DUPLICATES / 1000000000" | bc -l)
                BRANCHES_MAP[$KEY_COMMIT]=$(printingRemoteBranchesDetails  "$MERGED" "$ID_COMMIT" "$TIME_STRING" "$AUTHOR_COMMIT" "$LOCAL_BRANCH" "$COMMON_ANCESTOR" "$MESSAGE_COMMIT")
                BRANCHES_KEYS+=("$KEY_COMMIT")
            fi
            BRANCHES_PENDING=$((BRANCHES_PENDING - 1))
        done
        local SORTED_BRANCHES=$(echo "${BRANCHES_KEYS[@]}" | $WS_CONFIG_HOME/py/util/sort_numbers.py)

        if [ -f "$REMOTE_BRANCHES_OUTPUT" ]; then
            rm $REMOTE_BRANCHES_OUTPUT
        fi
        # Print the sorted array
        while read -r branch; do
            echo "${BRANCHES_MAP[$branch]}" >> "$REMOTE_BRANCHES_OUTPUT"
        done < <(echo "$SORTED_BRANCHES")
        code "$REMOTE_BRANCHES_OUTPUT"
        
        unset -f printingRemoteBranchesDetails
}
ws_tip "remoteBranchesDetails" "get details of the branches in the repo"