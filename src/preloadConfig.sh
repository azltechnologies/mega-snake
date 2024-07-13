PRELOAD_SH="$WS_TEMP/preload.sh"
if [ ! -d "$WS_TEMP" ]; then
    mkdir -p "$WS_TEMP"
fi
if [ ! -f "$PRELOAD_SH" ]; then
    touch "$PRELOAD_SH"
    echo "ws_advice 'add your preload configurations in $PRELOAD_SH'" > "$PRELOAD_SH"
    echo "#uncomment the following lines as needed"  >> "$PRELOAD_SH"
    echo "#  ws_success 'Use 'ws_success' to print into the console in this format'"  >> "$PRELOAD_SH"
    echo "#  ws_info 'Use 'ws_info' to print into the console in this format'"  >> "$PRELOAD_SH"
    echo "#  ws_warning 'Use 'ws_warning' to print into the console in this format'"  >> "$PRELOAD_SH"
    echo "#  ws_error 'Use 'ws_error' to print into the console in this format'"  >> "$PRELOAD_SH"
    echo "#  ws_advice 'Use 'ws_advice' to print into the console in this format'"  >> "$PRELOAD_SH"
    echo "\n\n\n#specify gradle version number to use"  >> "$PRELOAD_SH"
    echo "#  export VER_GRADLE=\n"  >> "$PRELOAD_SH"
    echo "#specify java version number to use"  >> "$PRELOAD_SH"
    echo "#  export VER_JAVA=\n"  >> "$PRELOAD_SH"
    echo "#specify if the terminal should attempt to login to gcloud using 'application-default login'. Possible values are 'true' and 'false'"  >> "$PRELOAD_SH"
    echo "#  export CHECK_GCLOUD=\n"  >> "$PRELOAD_SH"
    echo "#specify if git should untrack changes in gradle.properties file. Possible values are 'true' and 'false'"  >> "$PRELOAD_SH"
    echo "#  export UNTRACK_PROPS=\n"  >> "$PRELOAD_SH"
    chmod +x "$PRELOAD_SH"
    source "$PRELOAD_SH"
    code "$PRELOAD_SH"
else
    source "$PRELOAD_SH"
fi

preload(){
    source "$PRELOAD_SH"
}

ws_advice "you can use the  'preload' function to reload the configuration"clear