createDiffTree() {
    local CURRENT_BRANCH=$(git rev-parse HEAD)
    # checking if $1 exists
    if [ -z "$1" ]; then
        local MAIN_BRANCH=$(git remote show origin | sed -n '/HEAD branch/s/.*: //p')
    else
        # Check if the commit hash is valid
        if git cat-file -t "$1" 2>/dev/null | grep -q commit; then
            local MAIN_BRANCH=$1
        else
            ws_error "Invalid commit hash"
            return 1
        fi
    fi
    local DIFF_TREE_FILE="diff_tree.txt"
    local DIFF_COMMIT_FILE="diff_commit.txt"
    local DIFF_TREE_DUMMY_REPO="$DIFF_TREE_OUTPUT/diff_tree_dummy_repo"
    local SYMBOLS
    declare -A SYMBOLS
    SYMBOLS[A]="🅐"
    SYMBOLS[M]="🅜"
    SYMBOLS[D]="🅓"
    SYMBOLS[R]="🅡"
    SYMBOLS[C]="🅒"
    SYMBOLS[T]="🅣"
    SYMBOLS[U]="🅤"

    declare -A SYMBOLS_VALUES
    SYMBOLS_VALUES[A]=0
    SYMBOLS_VALUES[M]=0
    SYMBOLS_VALUES[D]=0
    SYMBOLS_VALUES[R]=0
    SYMBOLS_VALUES[C]=0
    SYMBOLS_VALUES[T]=0
    SYMBOLS_VALUES[U]=0

    declare -A SYMBOLS_DESC
    SYMBOLS_DESC[A]="FILES ADDED"
    SYMBOLS_DESC[M]="FILES MODIFED"
    SYMBOLS_DESC[D]="FILES DELETED"
    SYMBOLS_DESC[R]="FILES RENAMED"
    SYMBOLS_DESC[C]="FILES COPIED"
    SYMBOLS_DESC[T]="FILES TYPECHANGED"
    SYMBOLS_DESC[U]="FILES UNMERGED"

    if [ -d "$DIFF_TREE_OUTPUT" ]; then
        rm -rf $DIFF_TREE_OUTPUT
        mkdir -p $DIFF_TREE_DUMMY_REPO
    fi

    RAW_DIFF=()
    while read -r record; do
        RAW_DIFF+=("$record")
    done < <(git diff-tree -r $MAIN_BRANCH $CURRENT_BRANCH)

    local File_class
    # Define the Person "class"
    declare -A File_class
    declare -A File_classes

    # Constructor
    File_class.new() {
        local st=$1
        local pt=$2
        File_class["STATUS"]="$1"
        File_class["PATH"]="$2"
    }

    # Method to get the file status
    File_class.getStatus() {
        echo "${File_class["STATUS"]}"
    }
    # Method to get the file path
    File_class.getPath() {
        echo "${File_class["PATH"]}"
    }
    files=()
    local i=0
    echo "size of raw diff: ${#RAW_DIFF[@]}"
    for RECORD in "${RAW_DIFF[@]}"; do
        local STATUS_FILE=$(echo "$RECORD" | awk '{print $5}')
        STATUS_FILE="${STATUS_FILE##*( )}"
        SYMBOLS_VALUES[$STATUS_FILE]=$((SYMBOLS_VALUES[$STATUS_FILE] + 1))
        local PATH_FILE=$(echo "$RECORD" | awk '{print $6}')
        File_class.new "$STATUS_FILE" "$PATH_FILE"
        for key in "${!File_class[@]}"; do
            File_classes[$i, $key]="${File_class[$key]}"
        done
        ((i++))
    done

    echo "size of file classes: ${#File_classes[@]}"
    for ((j = 0; j < $i; j++)); do
        local KEY_PATH=${File_classes[$j, "PATH"]}
        local KEY_STATUS=${File_classes[$j, "STATUS"]}
        local SYMBOL=${SYMBOLS[$KEY_STATUS]}
        local NEW_PATH_FILE="$DIFF_TREE_DUMMY_REPO/$KEY_PATH - $SYMBOL"
        local DIR_PATH=$(dirname "$NEW_PATH_FILE")
        mkdir -p "$DIR_PATH"
        touch $NEW_PATH_FILE
    done

    local CHANGES="\n${#RAW_DIFF[@]} files changed\n"
    for key in "${!SYMBOLS_VALUES[@]}"; do
        local qty="${SYMBOLS_VALUES[$key]}"
        if [ "$qty" -eq 0 ]; then
            continue
        fi
        local desc="${SYMBOLS_DESC[$key]}"
        local symbol="${SYMBOLS[$key]}"
        CHANGES="$CHANGES$symbol $desc: $qty\n"
    done

    # Use a subshell to change directory temporarily
    (
        cd "$DIFF_TREE_DUMMY_REPO" || exit
        tree -a --noreport . >"../$DIFF_TREE_FILE"
        echo -e "$CHANGES" >>"../$DIFF_TREE_FILE"
        code "../$DIFF_TREE_FILE"
        git log --pretty=format:"%ad %H%n%B" --date=short $CURRENT_BRANCH...$MAIN_BRANCH >"../$DIFF_COMMIT_FILE"
        code "../$DIFF_COMMIT_FILE"
    )
    ws_success "Diff tree created"
}
ws_tip "createDiffTree" "create a diff tree of the current branch against master"
