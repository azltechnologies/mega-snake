
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

ws_tip() {
    # Define color codes
    local GREEN='\033[0;32m'
    local RED='\033[0;31m'
    local YELLOW='\033[0;33m'
    local NC='\033[0m' # No Color
    echo -e "${GREEN}use the ${RED}'$1'${GREEN} function to ${YELLOW}$2${NC}"
}

endFormating() {
    unset -f ws_success
    unset -f ws_info
    unset -f ws_warning
    unset -f ws_error
    unset -f ws_advice
    unset -f endFormating
}
