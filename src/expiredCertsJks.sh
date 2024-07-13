export PAR="/Users/carlosmorales/IdeaProjects/ocm_pd_totf-api_store-information-api/workspace_temp/certs/tls-truststore.jks"
findExpiredJKSAliases(){
    {
        FUN=$0
        function getHelp(){
            ws_advice "Usage: $FUN [OPTIONS] <JKS_PATH>"
            ws_advice "OPTIONS:"
            ws_advice "  [-h | --help]: Display this help message and exit"
            ws_advice "  [[-p | --custom-pass] VALUE]: Use a custom password instead of the default 'changeit'"
        }
        function error(){
            ws_error "Error: $1"
            return 1
        }
        while [[ $# -gt 0 ]]; do
            local arg="$1"
            case $arg in
                --help | -h)
                    getHelp
                    return 0
                    ;;
                --custom-pass | -p)
                    if [[ -n "$2" ]]; then
                        local JKS_PASS="$2"
                        shift 2
                    else
                        error "Option --custom-pass requires an argument."
                    fi
                ;;
                *)
                    if [[ $# -ne 1 ]]; then
                        error "Invalid long option: $arg"
                    else
                        break
                    fi
                ;;
            esac
        done
        # Check if at least the JKS_PATH is provided
        if [ $# -lt 1 ]; then
            getHelp
            error "not enough parameters"
        fi
        # The last parameter is the path to the JKS file
        local JKS_PATH="$1"
        ws_info "JKS_PATH: $JKS_PATH"
        # Use the default password if none is provided
        if [ -z "$JKS_PASS" ]; then
            local JKS_PASS="changeit"
        fi
        ws_info "JKS_PASS: $JKS_PASS"


        # Check if keytool is available
        if ! command -v keytool &> /dev/null; then
            error "keytool could not be found. Please ensure Java is installed and keytool is in your PATH."
        fi

        # checking if command passes
        if keytool -v -list -keystore "$JKS_PATH" -storepass "$JKS_PASS" >/dev/null; then
            ws_success "Validation of parameters in keytool command succed."
        else
            error "keytool command failed on implementing parameters.."
        fi

        keytool -v -list -keystore "$JKS_PATH" -storepass "$JKS_PASS" >/dev/null
        if [ $? -eq 0 ]; then
            ws_success "Command succeeded."
        else
            error "Command failed with status $?."
        fi

        # Check each alias for expiration
        for ALIAS in $(keytool -v -list -keystore "$JKS_PATH" -storepass "$JKS_PASS" 2>/dev/null | grep -Eo 'Alias name: [^,]+' | grep -Eo '\S+$'); do
        #for ALIAS in $ALIASES; do
            ws_info "Checking alias: $ALIAS"
            # Extract the expiration date of the certificate
            #keytool -list -v -keystore "$JKS_PATH" -storepass "$JKS_PASS" -alias "$ALIAS"
            local FROM=$(keytool -list -v -keystore "$JKS_PATH" -storepass "$JKS_PASS" -alias "$ALIAS" | ggrep -Po 'Valid from: [^,]+(?=\suntil)' | sed 's/^Valid from: //')
            local UNTIL=$(keytool -list -v -keystore "$JKS_PATH" -storepass "$JKS_PASS" -alias "$ALIAS" | grep -Eo 'until: [^,]+$' | sed 's/^until: //')
            local CURRENT_DATE_SECS=$(gdate "+%s")
            local COMPARISON=$(echo "$(gdate -d "${FROM}" +%s) <= $CURRENT_DATE_SECS && $CURRENT_DATE_SECS <= $(gdate -d "${UNTIL}" +%s)")
            if echo "$COMPARISON" | bc -l | grep -q 1; then
                ws_success "Certificate with alias $ALIAS is valid."
            else
                ws_warning "Certificate with alias $ALIAS is expired."
                ws_advice "delete current certificate and add a new one. Please run the following commands:"
                ws_advice "   keytool -delete -alias $ALIAS -keystore $JKS_PATH -storepass $JKS_PASS"
                ws_advice "   keytool -import -alias $ALIAS -file <CERTIFICATE_FILE> -keystore $JKS_PATH -storepass $JKS_PASS"
            fi
        done
    } always {
        unfunction -m "getHelp"
    }
}
ws_advice "You can use findExpiredJKSAliases JKS_PATH to check if the certificates in the JKS file are expired" 