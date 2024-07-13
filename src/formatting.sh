
ws_success() {
    tput -T xterm-256color setaf 51
    echo "$1"
    tput -T xterm-256color sgr0
}

ws_info() {
    tput -T xterm-256color setaf 4
    echo "$1"
    tput -T xterm-256color sgr0
}

ws_warning() {
    tput -T xterm-256color setaf 3
    echo "$1"
    tput -T xterm-256color sgr0
}

ws_error() {
    tput -T xterm-256color setaf 1
    echo "$1"
    tput -T xterm-256color sgr0
}

ws_advice() {
    tput -T xterm-256color setaf 2
    echo "$1"
    tput -T xterm-256color sgr0
}

endFormating() {
    unset -f ws_success
    unset -f ws_info
    unset -f ws_warning
    unset -f ws_error
    unset -f ws_advice
    unset -f endFormating
}
