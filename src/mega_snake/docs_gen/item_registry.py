"""The catalogue of installable agent assets, and how each one is rendered and placed on disk.

An **item** is one thing an agent runtime discovers by reading the YAML frontmatter at the top of a
Markdown file. Two kinds exist, and the difference is not cosmetic -- they have different shapes on
disk, and the shape differs per runtime too:

| Kind | GitHub Copilot | Claude |
| --- | --- | --- |
| ``skill`` | ``.github/skills/<name>/SKILL.md`` | ``.claude/skills/<name>/SKILL.md`` |
| ``agent`` | ``.github/agents/<name>.agent.md`` | ``.claude/agents/<name>.md`` |

A skill owns a **directory** and may hold several files; an agent is a **single file**, and even its
extension is runtime-specific. ``ITEM_LAYOUT`` is the single place that knows this, so nothing else
has to branch on the kind: callers ask for ``item_targets`` (what to write, and where) and
``tracking_target`` (what to hand git), and get the right shape back either way.

**Dependencies are declared, resolved transitively, and always reported.** A task skill that drives
mgsnake commands is useless to an assistant that does not know those commands exist, so it requires
the CLI skill and installing one installs both. An agent may likewise bundle skills that are
meaningless on their own. Resolving that silently would leave files on disk the user never asked
for, so ``expand_items`` returns the closure and the caller names what it added and why.

**A hidden item is installable but not offered.** Setting ``hidden=True`` keeps an item out of the
interactive list while leaving it reachable through a dependency and through ``--skill``. That is
what a bundled component wants: nobody should install it on its own by accident, but refreshing it
directly must stay possible, or the only way to update it would be to reinstall its parent.
"""

from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Callable, Iterable, Literal, Optional

from mega_snake.constants import DOCS_FILE_SUFFIX, MODULE_NAME, RESOURCES_DIR, SKILLS_DIR
from mega_snake.docs_gen.generate_docs import introspected_commands
from mega_snake.docs_gen.markdown_writer import render_index, render_markdown
from mega_snake.util.formatting import InternalStateError

# Files a skill directory may hold. SKILL.md is what the runtimes read; REFERENCE_FILE is the
# on-demand half, written only by the skill that has one.
SKILL_FILE: str = "SKILL.md"
REFERENCE_FILE: str = "reference.md"

# The agent runtimes this command installs for, and the directory each one reads from.
RUNTIME_COPILOT: str = "copilot"
RUNTIME_CLAUDE: str = "claude"
RUNTIME_ROOT: dict[str, Path] = {RUNTIME_COPILOT: Path(".github"), RUNTIME_CLAUDE: Path(".claude")}
RUNTIME_LABEL: dict[str, str] = {RUNTIME_COPILOT: "GitHub Copilot", RUNTIME_CLAUDE: "Claude"}
# Deterministic order: --check iterates it, and so does every state report.
ALL_RUNTIMES: tuple[str, ...] = (RUNTIME_COPILOT, RUNTIME_CLAUDE)

# What kind of asset an item is. It decides the directory *and* the on-disk shape, so it is not a
# label: see ITEM_LAYOUT below.
ItemKind = Literal["skill", "agent"]
KIND_SKILL: ItemKind = "skill"
KIND_AGENT: ItemKind = "agent"


@dataclass(frozen=True)
class ItemLayout:
    """Where one kind of item lives, and what its file is called, per runtime.

    Parameters:
        directory: Sub-directory of the runtime root that holds this kind.
        own_directory: Whether each item gets a directory of its own (a skill) or is a single file
            sitting directly in ``directory`` (an agent).
        file_suffix: Extension per runtime, for the single-file kinds. Copilot reads
            ``<name>.agent.md`` while Claude reads ``<name>.md``, so this cannot be one constant.

    Raises:
        None

    Returns:
        None
    """

    directory: str
    own_directory: bool
    file_suffix: dict[str, str]


ITEM_LAYOUT: dict[ItemKind, ItemLayout] = {
    KIND_SKILL: ItemLayout(directory="skills", own_directory=True, file_suffix={}),
    KIND_AGENT: ItemLayout(
        directory="agents",
        own_directory=False,
        # Not symmetric, and getting it wrong writes a file the runtime silently never reads.
        file_suffix={RUNTIME_COPILOT: ".agent.md", RUNTIME_CLAUDE: ".md"},
    ),
}


def _frontmatter(item: "Item", body: str) -> str:
    """Prepend the YAML frontmatter that makes a Markdown file a discoverable skill.

    The description is emitted as a double-quoted scalar because a plain YAML scalar may not contain
    a colon followed by a space, which this prose can easily reacquire the next time it is edited.

    Parameters:
        item: The item whose name and description head the document.
        body: The Markdown body to place under the frontmatter.

    Raises:
        None

    Returns:
        str: The complete document, frontmatter first.
    """
    return f'---\nname: {item.name}\ndescription: "{item.description}"\n---\n\n{body}'


def _fragment_path(name: str) -> Path:
    """Resolve the packaged body of a task skill.

    Read through ``importlib.resources`` rather than from a path derived at runtime: this command is
    ``no_init``, so ``AppProperties`` — and with it ``get_property`` — is never built for it.

    Parameters:
        name: The skill name, which is also its fragment file stem.

    Raises:
        None

    Returns:
        Path: The packaged fragment path.
    """
    return Path(str(files(MODULE_NAME).joinpath(RESOURCES_DIR, SKILLS_DIR, f"{name}{DOCS_FILE_SUFFIX}")))


def render_cli_skill(item: "Item") -> dict[str, str]:
    """Render the CLI skill: a compact index in SKILL.md, the full reference beside it.

    One walk of the CLI, two projections of its result. Introspecting twice would let the two
    documents disagree about which commands exist, which is the one failure a generated document must
    not have.

    Parameters:
        item: The item being rendered.

    Raises:
        None

    Returns:
        dict[str, str]: File name to content, for every file this skill is made of.
    """
    # Lazy, and for the same reason the catalogue itself is: the preamble is content, it lives in
    # `item_catalog`, and that module imports this one for the model. See `catalogue`.
    from mega_snake.docs_gen.item_catalog import CLI_SKILL_PREAMBLE

    commands = introspected_commands()
    return {
        SKILL_FILE: _frontmatter(item, f"{CLI_SKILL_PREAMBLE}\n\n{render_index(commands)}"),
        REFERENCE_FILE: render_markdown(commands),
    }


def render_task_skill(item: "Item") -> dict[str, str]:
    """Render a task skill from its packaged prose fragment.

    Parameters:
        item: The item being rendered.

    Raises:
        InternalStateError: If the fragment is missing from the installed package, which means the
            distribution was built without a file the registry declares.

    Returns:
        dict[str, str]: File name to content, for the single file this skill is made of.
    """
    fragment: Path = _fragment_path(item.name)
    if not fragment.is_file():
        # The registry and the packaged resources ship together in the same wheel, so a declared
        # skill with no fragment is a packaging defect and never something the user can supply.
        raise InternalStateError(f"Skill fragment {fragment} is missing from the package. This is a bug.")
    return {SKILL_FILE: _frontmatter(item, fragment.read_text(encoding="utf-8").strip())}


@dataclass(frozen=True)
class Item:
    """One installable agent asset: a skill, or an agent.

    Parameters:
        name: The item name; also its directory or file stem, and its fragment file stem.
        summary: One line shown beside the name in the selection list.
        description: The frontmatter description telling an assistant when the item applies.
        render: Builds the item's files as a ``{file name: content}`` mapping. For a single-file kind
            the mapping holds exactly one entry and its key is ignored, since the name on disk is
            decided by the layout and the runtime.
        kind: Skill or agent. Decides the directory and the on-disk shape (``ITEM_LAYOUT``).
        requires: Names of items that must be installed alongside this one.
        hidden: When True the item is never offered in the interactive list. It is still installed as
            a dependency, and still reachable by name through the flag -- which is deliberate: a
            component that can only be refreshed by reinstalling its parent has no update path of
            its own.

    Raises:
        None

    Returns:
        None
    """

    name: str
    summary: str
    description: str
    render: Callable[["Item"], dict[str, str]]
    kind: ItemKind = field(default=KIND_SKILL)
    requires: tuple[str, ...] = field(default=())
    hidden: bool = field(default=False)

    @property
    def layout(self) -> ItemLayout:
        """The on-disk shape for this item's kind.

        Parameters:
            None

        Raises:
            None

        Returns:
            ItemLayout: The layout registered for ``kind``.
        """
        return ITEM_LAYOUT[self.kind]

    def files(self) -> dict[str, str]:
        """Render every file this item is made of.

        Parameters:
            None

        Raises:
            InternalStateError: Propagated by an item whose packaged fragment is missing.

        Returns:
            dict[str, str]: File name to content.
        """
        return self.render(self)


def tracking_target(item: Item, runtime: str) -> Path:
    """Resolve the single path git should be told about for this item under one runtime.

    A skill owns a directory, so the directory is what gets excluded; an agent is one file among
    others in a shared folder, so excluding its folder would hide every agent the user has, mgsnake's
    or not. Returning the right granularity per kind is the whole reason this is not a one-liner at
    the call site.

    Parameters:
        item: The item being installed.
        runtime: One of ``ALL_RUNTIMES``.

    Raises:
        KeyError: If the runtime is unknown, or the kind has no suffix for it.

    Returns:
        Path: The directory (skill) or file (agent) to hand to the git ignore helpers.
    """
    base: Path = RUNTIME_ROOT[runtime] / item.layout.directory
    if item.layout.own_directory:
        return base / item.name
    return base / f"{item.name}{item.layout.file_suffix[runtime]}"


def item_targets(item: Item, runtime: str, files: dict[str, str]) -> dict[Path, str]:
    """Resolve every path this item writes under one runtime, with the content for each.

    Parameters:
        item: The item being installed.
        runtime: One of ``ALL_RUNTIMES``.
        files: The rendered content, per file name, as ``Item.files`` returned it.

    Raises:
        InternalStateError: If a single-file item rendered more than one file, which would mean the
            registry paired a multi-file renderer with a kind that has nowhere to put the rest.
        KeyError: If the runtime is unknown, or the kind has no suffix for it.

    Returns:
        dict[Path, str]: Absolute-from-the-project-root path to content.
    """
    target: Path = tracking_target(item, runtime)
    if item.layout.own_directory:
        return {target / name: content for name, content in files.items()}
    if len(files) != 1:
        raise InternalStateError(
            f"Item '{item.name}' is a {item.kind}, which is a single file, but it rendered "
            f"{len(files)} of them. This is a bug."
        )
    return {target: next(iter(files.values()))}


def catalogue() -> dict[str, Item]:
    """Return the registered catalogue, keyed by name, in declaration order.

    The import is deliberately **lazy**. ``item_catalog`` holds the content and imports this module
    for the model, so a module-level import here would close the cycle. Deferring it to call time is
    the same pattern ``generate_docs.introspected_commands`` uses for the root CLI group, and for the
    same reason: the content depends on the model, never the other way round.

    Parameters:
        None

    Raises:
        None

    Returns:
        dict[str, Item]: Every registered item, keyed by name.
    """
    from mega_snake.docs_gen.item_catalog import ITEMS

    return {item.name: item for item in ITEMS}


def item_names() -> list[str]:
    """List every registered item name, hidden ones included, in catalogue order.

    This is the set a **name** may legitimately resolve to: the ``--skill`` flag accepts it in full,
    because a hidden item still needs a way to be refreshed on its own. Use ``selectable_names`` for
    anything a user picks from a list.

    Parameters:
        None

    Raises:
        None

    Returns:
        list[str]: Every item name.
    """
    return list(catalogue())


def selectable_names() -> list[str]:
    """List the items a user may choose from, in catalogue order.

    Hidden items are omitted: they are components of something else, and offering them on their own
    invites installing a fragment that does nothing by itself.

    Parameters:
        None

    Raises:
        None

    Returns:
        list[str]: The names of the items that are offered interactively.
    """
    return [name for name, item in catalogue().items() if not item.hidden]


def get_item(name: str) -> Item:
    """Look an item up by name.

    Parameters:
        name: The item name.

    Raises:
        KeyError: If no item carries that name.

    Returns:
        Item: The registered item.
    """
    return catalogue()[name]


def bundled_with(name: str, registry: Optional[dict[str, Item]] = None) -> list[str]:
    """List the items that come along when this one is installed, excluding itself.

    The inverse view of ``required_by``: that one answers "why did this arrive", this one answers
    "what will arrive with it", which is what the selection list has to show *before* the user
    chooses. An item bundling three components that appear unannounced is indistinguishable from a
    defect the moment the user looks at the working tree.

    Parameters:
        name: The item whose dependencies should be listed.
        registry: Catalogue to resolve against; defaults to the real one.

    Raises:
        KeyError: If the name, or anything it requires, is not registered.

    Returns:
        list[str]: The other items installed alongside it, in catalogue order.
    """
    return [resolved for resolved in expand_items([name], registry) if resolved != name]


def expand_items(names: Iterable[str], registry: Optional[dict[str, Item]] = None) -> list[str]:
    """Resolve a selection together with everything it requires, at any depth.

    The expansion is transitive on purpose: today no skill requires one that requires a third, so a
    single pass over ``requires`` would be enough — but the depth would then be an assumption baked
    into every call site, and a skill requiring a future task skill would silently arrive without the
    CLI skill that one needs. Doing it once here keeps the depth a property of this function alone.
    This mirrors ``ProjectStack.expand``, which resolves the same shape of graph for stacks.

    The result keeps **catalogue order**, not the order the user typed: a required skill has to be
    installed whether it was asked for or not, so the natural reading order is the registry's own.

    Parameters:
        names: The selected skill names.
        registry: Catalogue to resolve against; defaults to the real one. Injectable so the
            resolution can be tested against graphs deeper than the shipped registry has.

    Raises:
        KeyError: If a selected or required name is not registered.

    Returns:
        list[str]: The selection plus every skill reachable through ``requires``, in catalogue order.
    """
    known: dict[str, Item] = catalogue() if registry is None else registry
    resolved: set[str] = set()
    pending: list[str] = list(names)
    while pending:
        current: str = pending.pop()
        if current in resolved:
            continue
        resolved.add(current)
        pending.extend(required for required in known[current].requires if required not in resolved)
    return [name for name in known if name in resolved]


def required_by(names: Iterable[str], registry: Optional[dict[str, Item]] = None) -> dict[str, list[str]]:
    """Map each skill that was pulled in by a dependency to the selections that require it.

    The caller reports this to the user. Installing a skill nobody asked for is the right behaviour
    but never an acceptable surprise: files appear in the working tree, and without a line naming
    what dragged them in the user has no way to tell an intended install from a bug.

    Parameters:
        names: The skill names the user actually selected.
        registry: Catalogue to resolve against; defaults to the real one.

    Raises:
        KeyError: If a selected or required name is not registered.

    Returns:
        dict[str, list[str]]: Added skill name to the selected names that required it, in catalogue
            order; empty when the selection was already closed under ``requires``.
    """
    known: dict[str, Item] = catalogue() if registry is None else registry
    selected: list[str] = list(names)
    added: dict[str, list[str]] = {}
    for name in expand_items(selected, known):
        if name in selected:
            continue
        reasons: list[str] = [
            candidate for candidate in selected if name in expand_items([candidate], known) and name != candidate
        ]
        added[name] = reasons
    return added
