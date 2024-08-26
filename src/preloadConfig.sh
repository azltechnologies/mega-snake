PRELOAD_SH="$WS_TEMP/preload.sh"
if [ ! -d "$WS_TEMP" ]; then
    mkdir -p "$WS_TEMP"
fi
if [ ! -f "$PRELOAD_SH" ]; then
    touch "$PRELOAD_SH"
    echo "ws_advice 'add your preload configurations in $PRELOAD_SH'" > "$PRELOAD_SH"
    echo "ws_tip 'ws_advice' 'print into the console in the following format'"  >> "$PRELOAD_SH"
    echo "ws_advice 'this is an advice message'"  >> "$PRELOAD_SH"
    echo "ws_tip 'ws_success' 'print into the console in the following format'"  >> "$PRELOAD_SH"
    echo "ws_success 'this is a success message'"  >> "$PRELOAD_SH"
    echo "ws_tip 'ws_info' 'print into the console in the following format'"  >> "$PRELOAD_SH"
    echo "ws_info 'this is an info message'"  >> "$PRELOAD_SH"
    echo "ws_tip 'ws_warning' 'print into the console in the following format'"  >> "$PRELOAD_SH"
    echo "ws_warning 'this is a warning message'"  >> "$PRELOAD_SH"
    echo "ws_tip 'ws_error' 'print into the console in the following format'"  >> "$PRELOAD_SH"
    echo "ws_error 'this is an error message'"  >> "$PRELOAD_SH"
    echo "#uncomment the following lines as needed"  >> "$PRELOAD_SH"
    echo "\n\n\n#specify gradle version number to use"  >> "$PRELOAD_SH"
    echo "#  export VER_GRADLE=\"false\"\n"  >> "$PRELOAD_SH"
    echo "#specify java version number to use"  >> "$PRELOAD_SH"
    echo "#  export VER_JAVA=\"false\"\n"  >> "$PRELOAD_SH"
    echo "#specify if the terminal should attempt to login to gcloud using 'application-default login'. Possible values are 'true' and 'false'"  >> "$PRELOAD_SH"
    echo "#  export CHECK_GCLOUD=false\n"  >> "$PRELOAD_SH"
    echo "#specify if git should untrack changes in gradle.properties file. Possible values are 'true' and 'false'"  >> "$PRELOAD_SH"
    echo "#  export UNTRACK_PROPS=false\n"  >> "$PRELOAD_SH"
    chmod +x "$PRELOAD_SH"
    source "$PRELOAD_SH"
    code "$PRELOAD_SH"
else
    source "$PRELOAD_SH"
fi

preload(){
    source "$PRELOAD_SH"
}

ws_tip "preload" "reload the configuration"