"""The catalogue itself: every installable item, and the prose that belongs to it.

Kept apart from ``item_registry`` on purpose. That module holds the model, the on-disk layouts and
the dependency resolution -- code that has no reason to change when the catalogue grows. This one
holds what *does* change every time an item is added: its entry, its summary, its frontmatter
description, and any body text that is generated rather than packaged.

Adding an item therefore touches this file and, for a task skill or an agent, its prose fragment
under ``resources/skills/``. It never touches the logic.
"""

from mega_snake.constants import APP_NAME
from mega_snake.docs_gen.item_registry import REFERENCE_FILE, Item, render_cli_skill, render_task_skill

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

JIRA_CONTINUE_DESCRIPTION: str = (
    "Resume work on a Jira story: download the board once with mgsnake, rebuild the story's context "
    "from its full comment history, agree on the next step, and write it to a context file the next "
    "session starts from. Use it when picking a story back up, when asked to continue an issue by "
    "its key, or when the last state of a piece of work has to be recovered before coding."
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
)
