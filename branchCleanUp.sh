remoteBranchesCleanUp(){

    while true; do
        local USER_INPUT
        local CMD
        echo "Do you want to rerun the remoteBranchesDetails function? (y/n): "
        read USER_INPUT
        USER_INPUT="${USER_INPUT[1]}"
        USER_INPUT=$(echo "$USER_INPUT" | tr '[:upper:]' '[:lower:]')
        if [[ $USER_INPUT == "y" || $USER_INPUT == "n" ]]; then
            break
        fi
        echo "Respond y or n to the question"
    done

    if [[ $USER_INPUT == "y" ]]; then
        CMD="remoteBranchesDetails"
        while true; do
            echo "Do you want to filter the results? (y/n): "
            read USER_INPUT
            USER_INPUT="${USER_INPUT[1]}"
            USER_INPUT=$(echo "$USER_INPUT" | tr '[:upper:]' '[:lower:]')
            if [[ $USER_INPUT == "y" || $USER_INPUT == "n" ]]; then
                break
            fi
            echo "Respond y or n to the question"
        done
        if [[ $USER_INPUT == "y" ]]; then
            CMD="$CMD -f"
        fi
    fi

    if [ ! -z "$CMD" ] && [[ -n $CMD ]]; then
        echo "running: $CMD"
        eval "$CMD"
    fi
    if [ -f "$REMOTE_BRANCHES_OUTPUT" ]; then
        local TEXT=$(cat $REMOTE_BRANCHES_OUTPUT)
        python3 /Users/carlosmorales/IdeaProjects/stuff/parse_remote_branches.py "$TEXT"
        echo $BRANCHES
    else
        echo "file $REMOTE_BRANCHES_OUTPUT doesn't exist, run remoteBranchesDetails function first"
        return 1
    fi
}
echo "Additionally, you can use remoteBranchesCleanUp to delete remote branches"