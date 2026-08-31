"""The catalogue itself: every installable item, and the prose that belongs to it.

Kept apart from ``item_registry`` on purpose. That module holds the model, the on-disk layouts and
the dependency resolution -- code that has no reason to change when the catalogue grows. This one
holds what *does* change every time an item is added: its entry, its summary, its frontmatter
description, and any body text that is generated rather than packaged.

Adding an item therefore touches this file and, for a task skill or an agent, its prose fragment
under ``resources/skills/``. It never touches the logic.
"""

from mega_snake.constants import APP_NAME
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
# One orchestrating agent and five components it bundles. Every one of them is Claude-only: their
# headers use vocabulary GitHub Copilot has no equivalent for -- forking the Explore and Plan agents,
# argument substitution between stages, and blocks that execute on invocation. Writing them for
# Copilot would install files it registers and then behaves nothing like what was authored, so they
# declare `runtimes` and `install-agent-items` refuses. The port is catalogued in §8.8 of the
# copilot instructions.
#
# The five components are `hidden`: none of them does anything on its own -- each is handed its
# inputs by the kingpin -- so offering them in the selection list would invite installing a part.

PROGRESS_FOLDER_NAME: str = "create-progress-folder"
PROGRESS_FILE_NAME: str = "create-progress-file"
SPOTTER_NAME: str = "comment-killer-spotter"
PLAYERMAKER_NAME: str = "comment-killer-playermaker"
HITMAN_NAME: str = "comment-killer-hitman"
KINGPIN_NAME: str = "comment-killer-kingpin"

COMMENT_KILLER_ITEMS: tuple[Item, ...] = (
    Item(
        name=PROGRESS_FOLDER_NAME,
        summary="Creates the mission folder every comment-killer report is written into.",
        description=(
            "Creates a progress folder in the mgsnake local configuration path so that you and your "
            "sub-agents can document the results of each task."
        ),
        render=render_task_skill,
        # It shells out to `mgsnake local-config-path`, so the CLI reference is a real dependency and
        # not a formality -- which is what carries the whole crew to the mgsnake skill transitively.
        requires=(CLI_SKILL_NAME,),
        hidden=True,
        runtimes=(RUNTIME_CLAUDE,),
        frontmatter={
            "user-invocable": False,
            "when_to_use": (
                "Use this skill when you need to create a progress folder for documenting the "
                "results of tasks performed by you and your sub-agents."
            ),
            "allowed-tools": "Bash",
        },
    ),
    Item(
        name=PROGRESS_FILE_NAME,
        summary="Creates one timestamped report file inside a mission folder.",
        description=(
            "Creates a progress file at the provided path to document progress, results, findings, "
            "or other information related to the assigned task."
        ),
        render=render_task_skill,
        # Its only argument is the folder the other skill returns, so it is meaningless without it.
        requires=(PROGRESS_FOLDER_NAME,),
        hidden=True,
        runtimes=(RUNTIME_CLAUDE,),
        frontmatter={
            "user-invocable": False,
            "when_to_use": (
                "Use this skill when you need to create a progress file to document the results of "
                "tasks performed by you or your sub-agents."
            ),
            "arguments": ["outputpath"],
            "allowed-tools": "Bash",
        },
    ),
    Item(
        name=SPOTTER_NAME,
        summary="Read-only Explore fork: decides whether a review comment is still valid.",
        description=(
            "Explores the codebase to determine whether a code review comment is still valid or has "
            "already been resolved, and documents the findings and relevant code context."
        ),
        render=render_task_skill,
        hidden=True,
        runtimes=(RUNTIME_CLAUDE,),
        frontmatter={
            "user-invocable": False,
            "context": "fork",
            "agent": "Explore",
            "allowed-tools": "Bash",
            "arguments": ["contextfile"],
            "when_to_use": (
                "Use this skill when you want to determine whether a code review comment is still "
                "valid or has already been resolved."
            ),
        },
    ),
    Item(
        name=PLAYERMAKER_NAME,
        summary="Read-only Plan fork: turns the spotter's findings into an implementation plan.",
        description=(
            "Creates a plan to address a code review comment that is still valid, based on the "
            "comment and the findings from comment-killer-spotter."
        ),
        render=render_task_skill,
        hidden=True,
        runtimes=(RUNTIME_CLAUDE,),
        frontmatter={
            "user-invocable": False,
            "effort": "high",
            "model": "opus",
            "context": "fork",
            "allowed-tools": "Bash",
            "agent": "Plan",
            "background": False,
            "arguments": ["contextfile", "spotterfile"],
            "when_to_use": (
                "Use this skill when you want to create a plan to address a code review comment that is still valid."
            ),
        },
    ),
    Item(
        name=HITMAN_NAME,
        summary="Carries out the plan, verifies it, and files its own report.",
        description=(
            "Executes the implementation plan created by comment-killer-playermaker to resolve a "
            "valid code review comment, including the required production and test code changes."
        ),
        render=render_task_skill,
        hidden=True,
        runtimes=(RUNTIME_CLAUDE,),
        frontmatter={
            "user-invocable": False,
            "context": "fork",
            "effort": "medium",
            "model": "sonnet",
            "background": False,
            "allowed-tools": (
                "Bash(uv run pytest) Bash(uv run ruff format:*) Bash(uv run ruff check:*) "
                "Bash(uv run mypy:*) Bash(ruff format:*) Bash(ruff check:*) Bash(mypy:*)"
            ),
            "permissionMode": "acceptEdits",
            "arguments": ["contextfile", "planfile", "hitfile"],
            "when_to_use": (
                "Use this skill when you have a plan to address a code review comment that is still "
                "valid and need to carry it out."
            ),
        },
    ),
    Item(
        name=KINGPIN_NAME,
        summary="Orchestrates the whole comment-killer run; installs the five components with it.",
        description=(
            "Orchestrates the comment-killer workflow by delegating investigation, planning, "
            "implementation, and verification to specialized skills."
        ),
        render=render_task_skill,
        kind=KIND_AGENT,
        # It delegates to all five, and the two progress skills carry the mgsnake dependency up.
        requires=(PROGRESS_FOLDER_NAME, PROGRESS_FILE_NAME, SPOTTER_NAME, PLAYERMAKER_NAME, HITMAN_NAME),
        runtimes=(RUNTIME_CLAUDE,),
        frontmatter={
            "tools": ["Skill", "Read", "Write", "Edit"],
            "permissionMode": "acceptEdits",
            "model": "haiku",
            "skills": [PROGRESS_FOLDER_NAME, PROGRESS_FILE_NAME, SPOTTER_NAME, PLAYERMAKER_NAME, HITMAN_NAME],
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
