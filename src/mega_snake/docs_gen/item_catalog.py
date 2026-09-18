"""The catalogue itself: every installable item, and the prose that belongs to it.

Kept apart from ``item_registry`` on purpose. That module holds the model, the on-disk layouts and
the dependency resolution -- code that has no reason to change when the catalogue grows. This one
holds what *does* change every time an item is added: its entry, its summary, its frontmatter
description, and any body text that is generated rather than packaged.

Adding an item therefore touches this file and, for a task skill or an agent, its prose fragment
under ``resources/skills/``. It never touches the logic.
"""

from mega_snake.constants import APP_NAME, HITMAN_AGENT, KINGPIN_AGENT, TRAPPER_AGENT
from mega_snake.docs_gen.item_registry import (
    KIND_AGENT,
    REFERENCE_FILE,
    RUNTIME_CLAUDE,
    Item,
    render_cli_skill,
    render_task_skill,
)

# The item that documents the CLI itself. It is named after the CLI, so the value is taken from
# APP_NAME rather than written again: a second literal would be free to drift the day the command is
# renamed, and the directory would then no longer match the tool it documents. The alias exists
# because "the item every task skill requires" is a different idea from "the command name", and the
# reporting code reads better naming the first.
CLI_SKILL_NAME: str = APP_NAME

CLI_SKILL_PREAMBLE: str = (
    f"Reference for the `{CLI_SKILL_NAME}` CLI (PyPI package `mega-snake`).\n"
    "\n"
    "The table below lists every command with its aliases and a one-line description. It is an\n"
    "index, not the documentation: it carries no options, defaults, output files or caveats.\n"
    "\n"
    "**Before running a command, read its full entry.** Two equivalent ways, cheapest first:\n"
    "\n"
    f"- `{CLI_SKILL_NAME} man <command>` — renders that one command's full reference in the terminal.\n"
    f"- `{REFERENCE_FILE}`, next to this file — the same reference for every command, as a file.\n"
    "\n"
    f"Read only the entry you need. `{CLI_SKILL_NAME} man <command>` is preferred: it returns a single\n"
    "command instead of the whole document, and it always reflects the installed version.\n"
    "\n"
    f"Every command also accepts `-h`/`--help`, and `{CLI_SKILL_NAME} --help` lists the commands."
)

CLI_SKILL_DESCRIPTION: str = (
    "Complete command reference for the mgsnake CLI (package mega-snake), covering every command, "
    "alias, option and documented behaviour. Use it when running, choosing or explaining an mgsnake "
    "command - VS Code workspace setup for Java, Gradle and Maven projects, git and release "
    "workflows, dependency vulnerability audits, GraphQL and keystore utilities, or shell "
    "integration."
)

JIRA_CONTINUE_SKILL_NAME: str = "jira-continue"
JIRA_PROGRESS_COMMENT_SKILL_NAME: str = "jira-progress-comment"

JIRA_CONTINUE_DESCRIPTION: str = (
    "Resume work on a Jira story: download the board once with mgsnake, rebuild the story's context "
    "from its full comment history, agree on the next step, and write it to a context file the next "
    "session starts from. Use it when picking a story back up, when asked to continue an issue by "
    "its key, or when the last state of a piece of work has to be recovered before coding."
)


# --- The comment-killer crew -------------------------------------------------------------------
#
# One orchestrating agent and the two henchmen it delegates to. The third henchman, the spotter, is
# not an item: it is the runtime's own Explore agent, launched with a brief the `comment-killer`
# command writes into the mission folder, so there is nothing to install for it and nothing in the
# user's repository to keep in step with the CLI.
#
# Every one of them is Claude-only: their headers use vocabulary GitHub Copilot has no equivalent
# for -- sub-agent delegation with per-agent tools, lifecycle hooks, and an initial prompt. Writing
# them for Copilot would install files it registers and then behaves nothing like what was authored,
# so they declare `runtimes` and `install-agent-items` refuses. The port is catalogued in section
# 8.8 of the copilot instructions.
#
# The henchmen are `hidden`: neither does anything on its own -- each is handed its files by the
# kingpin -- so offering them in the selection list would invite installing a part.
#
# The `hooks` entries call the CLI itself (`mgsnake comment-killer-guard ...`). That is what keeps
# the rules of the crew shipping and versioning with the command that drives it, instead of as
# scripts a user would have to keep in their own repository.


GIT_STATE_HOOK: dict[str, object] = {
    "PreToolUse": [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": f"{APP_NAME} comment-killer-guard git-state"}]}
    ]
}

COMMENT_KILLER_ITEMS: tuple[Item, ...] = (
    Item(
        name=TRAPPER_AGENT,
        summary="Writes the failing tests that pin what a review comment demands.",
        description=(
            "Henchman of the comment-killer crew. Writes the failing tests that pin the behaviour a "
            "still-valid code review comment demands, proves they fail today, and hands them over as "
            "the trap. Only the comment-killer-kingpin delegates to this agent."
        ),
        render=render_task_skill,
        kind=KIND_AGENT,
        hidden=True,
        runtimes=(RUNTIME_CLAUDE,),
        frontmatter={
            "tools": ["Read", "Write", "Edit", "Grep", "Glob", "Bash"],
            "model": "sonnet",
            "effort": "medium",
            "permissionMode": "acceptEdits",
            "color": "yellow",
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": f"{APP_NAME} comment-killer-guard git-state"}],
                    },
                    {
                        "matcher": "Edit|Write|NotebookEdit",
                        "hooks": [{"type": "command", "command": f"{APP_NAME} comment-killer-guard trapper"}],
                    },
                ]
            },
        },
    ),
    Item(
        name=HITMAN_AGENT,
        summary="Makes the trap pass, verifies against a baseline, and files its report.",
        description=(
            "Henchman of the comment-killer crew. Makes the trapper's failing tests pass for a "
            "still-valid code review comment, verifies the result with the project's own checks, and "
            "files its own report. Only the comment-killer-kingpin delegates to this agent."
        ),
        render=render_task_skill,
        kind=KIND_AGENT,
        hidden=True,
        runtimes=(RUNTIME_CLAUDE,),
        frontmatter={
            "tools": ["Read", "Edit", "Write", "Grep", "Glob", "Bash"],
            "model": "opus",
            "effort": "high",
            "permissionMode": "acceptEdits",
            "omitClaudeMd": True,
            "color": "red",
            "hooks": GIT_STATE_HOOK,
        },
    ),
    Item(
        name=KINGPIN_AGENT,
        summary="Runs a whole review-comment mission; installs the two henchmen with it.",
        description=(
            "Orchestrates the comment-killer workflow by relaying the crew's state machine to the "
            "henchman subagents: investigate, set the trap, spring it, report."
        ),
        render=render_task_skill,
        kind=KIND_AGENT,
        # It delegates to both, and neither is any use without it; and it drives the CLI's own
        # `comment-killer` command, so the reference that documents it travels along.
        requires=(CLI_SKILL_NAME, TRAPPER_AGENT, HITMAN_AGENT),
        runtimes=(RUNTIME_CLAUDE,),
        frontmatter={
            "tools": ["Agent", "Bash", "Write", "Read"],
            "permissionMode": "acceptEdits",
            "model": "haiku",
            # Hooks declared here are inherited by every subagent the kingpin spawns. That is what
            # guards the spotter, which is the runtime's own Explore agent and has no header to
            # declare a hook in; the henchmen keep their own git-state hook too, so they stay
            # guarded when used without the kingpin.
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {"type": "command", "command": f"{APP_NAME} comment-killer-guard kingpin"},
                            {"type": "command", "command": f"{APP_NAME} comment-killer-guard git-state"},
                        ],
                    }
                ]
            },
            "initialPrompt": (
                "Greet the boss in character. Remind them, in one or two lines, that this crew works "
                "TDD: it turns a code review comment into failing tests and then makes them pass, so "
                "it needs a project with a test suite, and it is not the tool for a comment no test "
                "could ever prove -- a rename, a rewording, a file move. Tell them the crew only runs "
                "what the project's permissions allow, and that granting these two beforehand is what "
                "keeps a mission from stopping to ask: "
                f"`Bash({APP_NAME} comment-killer:*)` for your own commands, and whatever the project's "
                "checks need for the henchmen (its test runner, its linter, its type checker). Either "
                "with `/permissions` or in the `permissions.allow` list of "
                "`.claude/settings.local.json`. Then ask for the code review comment to whack, and wait."
            ),
        },
    ),
)

JIRA_PROGRESS_COMMENT_DESCRIPTION: str = (
    "Write a progress comment on a Jira story, built from the commit range since a given baseline "
    "and merged with the author's own read of where the work stands. Use it when reporting a day's "
    "progress on an issue, when asked to comment on a story, or when a story's thread has to be "
    "brought up to date before handing the work over. Never publishes without approval."
)

# The installable catalogue, in the order the selection list shows it. The CLI skill comes first
# because every other one requires it.
ITEMS: tuple[Item, ...] = (
    Item(
        name=CLI_SKILL_NAME,
        summary="The mgsnake command reference: index plus the full reference beside it.",
        description=CLI_SKILL_DESCRIPTION,
        render=render_cli_skill,
    ),
    Item(
        name=JIRA_CONTINUE_SKILL_NAME,
        summary="Resume a Jira story from its comment history, and record the plan.",
        description=JIRA_CONTINUE_DESCRIPTION,
        render=render_task_skill,
        # It tells the assistant to run mgsnake commands, so it is useless on its own: without the
        # CLI skill the assistant has no way to learn what those commands accept or return.
        requires=(CLI_SKILL_NAME,),
    ),
    Item(
        name=JIRA_PROGRESS_COMMENT_SKILL_NAME,
        summary="Draft a progress comment for a Jira story from the day's commit range.",
        description=JIRA_PROGRESS_COMMENT_DESCRIPTION,
        render=render_task_skill,
        # It drives `diff-tree` and `jira-issues`, so it needs the reference that documents them.
        # It reads `current_story.md` when jira-continue produced one, but does not depend on it:
        # it can list the sprint itself, and a dependency that is not needed is one invented to look
        # tidy.
        requires=(CLI_SKILL_NAME,),
    ),
    *COMMENT_KILLER_ITEMS,
)
