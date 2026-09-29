"""Literals shared by the comment-killer crew's commands and guards.

Kept with the command rather than in the package's ``constants.py``: nothing outside this module
reads them, and the shared vocabulary file is for values several commands depend on. The agents'
names are the exception: `install-agent-items` installs them too, so they live there.
"""

from typing import Final

MISSION_DIR_NAME: Final[str] = "comment_killer"
# What `--mission` accepts: a mission folder's own name, never a path. The folders are named by the
# state machine itself (a timestamp, plus a suffix when two open in the same second), so a word of
# letters, digits, `_` and `-` covers every id it hands out and nothing a shell would expand or split.
MISSION_ID_PATTERN: Final[str] = r"[\w-]+"
TEST_PATTERN_KEY: Final[str] = "ck.test_pattern"
BRIEF_RESOURCE: Final[str] = "spotter.md"
CREW_DIR: Final[str] = "crew"

# The stages a mission walks, in order, and the file each one produces inside the mission folder.
STAGE_BRIEF: Final[str] = "brief"
STAGE_SPOTTER: Final[str] = "spotter"
STAGE_TRAPPER: Final[str] = "trapper"
STAGE_HITMAN: Final[str] = "hitman"
STAGE_DONE: Final[str] = "done"

STAGES: Final[tuple[str, ...]] = (STAGE_BRIEF, STAGE_SPOTTER, STAGE_TRAPPER, STAGE_HITMAN, STAGE_DONE)
FILE_NAMES: Final[dict[str, str]] = {
    STAGE_BRIEF: "01_brief.md",
    STAGE_SPOTTER: "02_map.md",
    STAGE_TRAPPER: "03_trap.md",
    STAGE_HITMAN: "04_hit.md",
}
SPOTTER_BRIEF_FILE: Final[str] = "00_spotter_brief.md"
STATE_FILE: Final[str] = ".state.json"

# The built-in agent the spotter stage is served by, and the model the kingpin must ask for when
# launching it. The crew's own agents are named in the package's constants.
SPOTTER_AGENT: Final[str] = "Explore"
SPOTTER_MODEL: Final[str] = "sonnet"

# How the spotter states its verdict, read from the top of its report.
VERDICT_SCAN_LINES: Final[int] = 15
STILL_VALID: Final[str] = "STILL VALID"
ALREADY_RESOLVED: Final[str] = "ALREADY RESOLVED"

# Statuses the crew script answers with; the kingpin's prompt keys its whole flow on these.
STATUS_WRITE: Final[str] = "write_file"
STATUS_LAUNCH: Final[str] = "launch"
STATUS_MISSING: Final[str] = "missing"
STATUS_DONE: Final[str] = "done"
STATUS_ERROR: Final[str] = "error"

# Guards, addressed by name on the command line, and the exit status a hook uses to refuse a call.
GUARD_KINGPIN: Final[str] = "kingpin"
GUARD_TRAPPER: Final[str] = "trapper"
GUARD_GIT_STATE: Final[str] = "git-state"
GUARD_OPT: Final[tuple[str, ...]] = (GUARD_KINGPIN, GUARD_TRAPPER, GUARD_GIT_STATE)
GUARD_COMMAND: Final[str] = "comment-killer-guard"
HOOK_BLOCK_CODE: Final[int] = 2
