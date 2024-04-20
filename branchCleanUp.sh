remoteBranchesCleanUp(){
    if [ -f "$REMOTE_BRANCHES_OUTPUT" ]; then
        local TEXT=$(cat $REMOTE_BRANCHES_OUTPUT)
        local BRANCHES=$(echo "$TEXT" | /Users/carlosmorales/IdeaProjects/stuff/parse_remote_branches.py)
        echo $BRANCHES
    fi
}
echo "Additionally, you can use remoteBranchesCleanUp to delete remote branches"