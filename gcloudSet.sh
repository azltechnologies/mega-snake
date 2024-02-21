setCloud(){
    echo 'checking if token file exists'
    local CRED_FILE='/Users/carlosmorales/.config/gcloud/application_default_credentials.json'
    local NEED_AUTH=0
    if [ -f "$CRED_FILE" ]; then
        local NOW=$(date +%s)
        local MODIFIED=$(stat -f %c $CRED_FILE)
        local TIME_DIFF=$((NOW - MODIFIED))
        echo "File exists!"
        if [ "$TIME_DIFF" -gt 3600 ]; then
            AUTH=1
        fi
    fi
    if [ "$NEED_AUTH" -eq 1 ]; then
        echo 'log in to gcloud please'
        gcloud auth application-default login
    else
        echo 'gcloud active session detected'
    fi
}