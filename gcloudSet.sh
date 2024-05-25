setCloud(){
    ws_info 'checking if token file exists'
    local CRED_FILE='/Users/carlosmorales/.config/gcloud/application_default_credentials.json'
    local NEED_AUTH=0
    if [ -f "$CRED_FILE" ]; then
        local NOW=$(date +%s)
        local MODIFIED=$(stat -f %c $CRED_FILE)
        local TIME_DIFF=$((NOW - MODIFIED))
        if [ "$TIME_DIFF" -gt 3600 ]; then
            NEED_AUTH=1
        fi
    else 
        NEED_AUTH=1
    fi
    if [ "$NEED_AUTH" -eq 1 ]; then
        ws_advice 'log in to gcloud please'
        gcloud auth application-default login
    else
        ws_info 'gcloud active session detected'
    fi
}