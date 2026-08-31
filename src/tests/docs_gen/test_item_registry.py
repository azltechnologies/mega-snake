"""Tests for the installable item catalogue, its layouts and its dependency resolution."""

from pathlib import Path
from typing import Callable, Optional
from unittest.mock import patch

import pytest

from mega_snake.docs_gen.item_registry import (
    REFERENCE_FILE,
    catalogue,
    SKILL_FILE,
    Item,
    expand_items,
    get_item,
    render_cli_skill,
    render_task_skill,
    required_by,
    item_names,
)
from mega_snake.docs_gen.item_catalog import CLI_SKILL_NAME, ITEMS
from mega_snake.util.formatting import InternalStateError

# Names that share no prefix with each other or with the real catalogue, so a substring comparison
# can never mistake one for another and no assertion can pass by colliding with a shipped skill.
ALPHA = "alpha-skill"
BETA = "beta-skill"
GAMMA = "gamma-skill"


def spec(
    name: str,
    *,
    requires: tuple[str, ...] = (),
    summary: str = "A skill for testing.",
    description: str = "Testing description.",
    render: Optional[Callable[[Item], dict[str, str]]] = None,
) -> Item:
    """Build a Item, defaulting every field a test does not assert on.

    Every field a test makes a claim about is passed explicitly by that test, so no assertion is ever
    satisfied by a value this builder chose invisibly.

    Parameters:
        name: The skill name.
        requires: The skills this one depends on.
        summary: The selection-list summary.
        description: The frontmatter description.
        render: The renderer; defaults to one returning a single trivial file.

    Raises:
        None

    Returns:
        Item: The built spec.
    """
    return Item(
        name=name,
        summary=summary,
        description=description,
        render=render or (lambda built: {SKILL_FILE: f"body of {built.name}"}),
        requires=requires,
    )


def registry_of(*specs: Item) -> dict[str, Item]:
    """Build a catalogue mapping in declaration order.

    Parameters:
        *specs: The specs to register.

    Raises:
        None

    Returns:
        dict[str, Item]: The catalogue, keyed by name.
    """
    return {built.name: built for built in specs}


# ---------------------------------------------------------------------------
# expand_items
# ---------------------------------------------------------------------------


def test_expand_items_returns_a_selection_that_needs_nothing_unchanged() -> None:
    """A skill with no dependencies expands to itself."""
    catalogue = registry_of(spec(ALPHA))

    assert expand_items([ALPHA], catalogue) == [ALPHA]


def test_expand_items_pulls_in_a_direct_dependency() -> None:
    """Selecting a skill that requires another installs both."""
    catalogue = registry_of(spec(ALPHA), spec(BETA, requires=(ALPHA,)))

    assert expand_items([BETA], catalogue) == [ALPHA, BETA]


def test_expand_items_resolves_dependencies_transitively() -> None:
    """A dependency of a dependency is installed too.

    The shipped catalogue is only one level deep, so this is asserted against an injected registry:
    a single non-recursive pass over ``requires`` would satisfy the direct case above and silently
    drop ALPHA here, which is precisely the defect the depth argument in the docstring warns about.
    """
    catalogue = registry_of(spec(ALPHA), spec(BETA, requires=(ALPHA,)), spec(GAMMA, requires=(BETA,)))

    resolved = expand_items([GAMMA], catalogue)

    assert resolved == [ALPHA, BETA, GAMMA], f"transitive dependency was dropped: {resolved}"
    assert ALPHA in resolved, "the second-level dependency is missing"


def test_expand_items_returns_catalogue_order_not_the_typed_order() -> None:
    """The result reads in registry order, whatever order the selection arrived in.

    A required skill has to be installed whether it was asked for or not, so ordering by what the
    user typed would put a dependency after the thing that needs it.
    """
    catalogue = registry_of(spec(ALPHA), spec(BETA), spec(GAMMA))

    assert expand_items([GAMMA, ALPHA], catalogue) == [ALPHA, GAMMA]


def test_expand_items_collapses_a_skill_reached_twice() -> None:
    """A dependency shared by two selections is installed once."""
    catalogue = registry_of(spec(ALPHA), spec(BETA, requires=(ALPHA,)), spec(GAMMA, requires=(ALPHA,)))

    assert expand_items([BETA, GAMMA], catalogue) == [ALPHA, BETA, GAMMA]


def test_expand_items_rejects_an_unregistered_name() -> None:
    """An unknown name is a KeyError, not a silently empty expansion."""
    catalogue = registry_of(spec(ALPHA))

    with pytest.raises(KeyError):
        expand_items(["nope"], catalogue)


# ---------------------------------------------------------------------------
# required_by
# ---------------------------------------------------------------------------


def test_required_by_is_empty_when_the_selection_needs_nothing() -> None:
    """Nothing is reported when the user already picked everything that will be installed."""
    catalogue = registry_of(spec(ALPHA), spec(BETA, requires=(ALPHA,)))

    assert required_by([ALPHA, BETA], catalogue) == {}


def test_required_by_names_the_selection_that_dragged_a_skill_in() -> None:
    """The added skill maps to the selections requiring it, so the message can explain itself."""
    catalogue = registry_of(spec(ALPHA), spec(BETA, requires=(ALPHA,)))

    assert required_by([BETA], catalogue) == {ALPHA: [BETA]}


def test_required_by_lists_every_reason_for_a_shared_dependency() -> None:
    """Two selections needing the same skill both appear as reasons."""
    catalogue = registry_of(spec(ALPHA), spec(BETA, requires=(ALPHA,)), spec(GAMMA, requires=(ALPHA,)))

    assert required_by([BETA, GAMMA], catalogue) == {ALPHA: [BETA, GAMMA]}


def test_required_by_reports_a_transitive_addition() -> None:
    """A skill pulled in two levels down is reported, not just the direct dependency."""
    catalogue = registry_of(spec(ALPHA), spec(BETA, requires=(ALPHA,)), spec(GAMMA, requires=(BETA,)))

    added = required_by([GAMMA], catalogue)

    assert set(added) == {ALPHA, BETA}, f"a transitive addition went unreported: {added}"
    assert added[ALPHA] == [GAMMA]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_render_cli_skill_writes_the_index_and_the_reference() -> None:
    """The CLI skill is two files, and only SKILL.md carries the frontmatter."""
    files = render_cli_skill(get_item(CLI_SKILL_NAME))

    assert set(files) == {SKILL_FILE, REFERENCE_FILE}, f"unexpected file set: {sorted(files)}"
    assert files[SKILL_FILE].startswith("---\n"), "SKILL.md is missing its frontmatter"
    assert not files[REFERENCE_FILE].startswith("---\n"), "the reference must not carry frontmatter"
    assert files[REFERENCE_FILE] != files[SKILL_FILE]


def test_render_task_skill_reads_the_packaged_fragment(tmp_path: Path) -> None:
    """A task skill's body is its packaged prose, under the frontmatter."""
    fragment = tmp_path / f"{ALPHA}.md"
    fragment.write_text("Body of the task skill.\n", encoding="utf-8")
    built = spec(ALPHA, description="When to use alpha.")

    with patch("mega_snake.docs_gen.item_registry._fragment_path", return_value=fragment):
        files = render_task_skill(built)

    assert set(files) == {SKILL_FILE}, "a task skill writes one file"
    assert files[SKILL_FILE] == f'---\nname: {ALPHA}\ndescription: "When to use alpha."\n---\n\nBody of the task skill.'


def test_render_task_skill_fails_when_the_fragment_is_not_packaged(tmp_path: Path) -> None:
    """A declared skill with no packaged body is a packaging defect, reported as such.

    It must not degrade into an empty skill: writing frontmatter with no body installs a file the
    runtime happily registers and that teaches the assistant nothing, with a successful exit.
    """
    missing = tmp_path / "absent.md"

    with (
        patch("mega_snake.docs_gen.item_registry._fragment_path", return_value=missing),
        pytest.raises(InternalStateError, match=str(missing)),
    ):
        render_task_skill(spec(ALPHA))


# ---------------------------------------------------------------------------
# The shipped catalogue
# ---------------------------------------------------------------------------


def test_every_declared_dependency_is_registered() -> None:
    """A `requires` entry naming an unregistered skill would raise only at install time."""
    for built in ITEMS:
        for required in built.requires:
            assert required in catalogue(), f"{built.name!r} requires unregistered {required!r}"


def test_every_task_skill_requires_the_cli_skill() -> None:
    """A skill that drives mgsnake is useless without the reference that documents it.

    Iterated over the whole catalogue rather than sampled, so a task skill added later without the
    dependency fails here instead of shipping an assistant that cannot read the commands it is told
    to run.
    """
    for built in ITEMS:
        if built.name == CLI_SKILL_NAME:
            continue
        assert CLI_SKILL_NAME in expand_items([built.name]), f"{built.name!r} does not pull in the CLI skill"


def test_item_names_are_valid_identifiers() -> None:
    """Both runtimes key a skill by its name, which is also its directory name."""
    for name in item_names():
        assert name == name.lower(), f"{name!r} is not lowercase"
        assert name.replace("-", "").isalnum(), f"{name!r} is not a slug"


def test_skill_descriptions_stay_quotable() -> None:
    """The description is emitted as a double-quoted YAML scalar, so it must not break one."""
    for built in ITEMS:
        assert '"' not in built.description, f"{built.name!r} has an unescaped quote in its description"
        assert "\n" not in built.description, f"{built.name!r} has a newline in its description"


def test_get_item_rejects_an_unknown_name() -> None:
    """An unregistered name is an error, never a silently empty skill."""
    with pytest.raises(KeyError):
        get_item("not-a-skill")


def test_fragment_path_resolves_inside_the_packaged_skills_directory() -> None:
    """A task skill's prose is read from the wheel, not from a path derived at runtime.

    The command is ``no_init``, so ``AppProperties`` is never built for it and ``get_property``
    would raise; resolving through ``importlib.resources`` is what makes it work for an installed
    user as well as in a source checkout.
    """
    from mega_snake.docs_gen.item_registry import _fragment_path

    resolved = _fragment_path(ALPHA)

    assert resolved.name == f"{ALPHA}.md"
    assert resolved.parent.name == "skills"
    assert resolved.parent.parent.name == "resources"


def test_skill_spec_files_delegates_to_its_own_renderer() -> None:
    """Each spec renders through the callable it declares, so the two kinds can differ."""
    built = spec(ALPHA, render=lambda target: {SKILL_FILE: f"rendered {target.name}"})

    assert built.files() == {SKILL_FILE: f"rendered {ALPHA}"}


def test_every_task_skill_has_its_fragment_packaged() -> None:
    """A registered task skill whose prose is not in the wheel would fail only at install time.

    Iterated over the whole catalogue, the same way ``test_every_command_has_a_fragment`` covers the
    docs fragments: a skill added to the registry without adding its file is caught here, naming the
    skill, instead of raising InternalStateError on a user's machine.
    """
    from mega_snake.docs_gen.item_registry import _fragment_path, render_task_skill

    for built in ITEMS:
        if built.render is not render_task_skill:
            continue
        assert _fragment_path(built.name).is_file(), f"{built.name!r} has no packaged fragment"


def test_every_task_skill_renders_a_non_empty_body() -> None:
    """Frontmatter over an empty body registers a skill that teaches the assistant nothing."""
    from mega_snake.docs_gen.item_registry import render_task_skill

    for built in ITEMS:
        if built.render is not render_task_skill:
            continue
        body = built.files()[SKILL_FILE].split("\n---\n", 1)[1]
        assert body.strip(), f"{built.name!r} renders an empty body"


# ---------------------------------------------------------------------------
# Kinds, layouts and on-disk shape
# ---------------------------------------------------------------------------

from mega_snake.docs_gen.item_registry import (  # noqa: E402
    ALL_RUNTIMES,
    ITEM_LAYOUT,
    KIND_AGENT,
    KIND_SKILL,
    RUNTIME_CLAUDE,
    RUNTIME_COPILOT,
    bundled_with,
    item_targets,
    selectable_names,
    tracking_target,
)

AGENT_BODY = "AGENT BODY"


def agent(name: str, *, requires: tuple[str, ...] = (), hidden: bool = False) -> Item:
    """Build an agent-kind item.

    Parameters:
        name: The item name.
        requires: The items it depends on.
        hidden: Whether it is kept out of the interactive list.

    Raises:
        None

    Returns:
        Item: The built item.
    """
    return Item(
        name=name,
        summary="An agent for testing.",
        description="Testing description.",
        render=lambda built: {"ignored": AGENT_BODY},
        kind=KIND_AGENT,
        requires=requires,
        hidden=hidden,
    )


def test_a_skill_owns_a_directory_and_an_agent_is_a_single_file() -> None:
    """The two kinds have different shapes on disk, which is why kind is not just a label."""
    assert ITEM_LAYOUT[KIND_SKILL].own_directory is True
    assert ITEM_LAYOUT[KIND_AGENT].own_directory is False
    assert ITEM_LAYOUT[KIND_SKILL].directory == "skills"
    assert ITEM_LAYOUT[KIND_AGENT].directory == "agents"


def test_skill_paths_are_the_same_shape_for_both_runtimes() -> None:
    """A skill is a folder holding SKILL.md, identically for Copilot and Claude."""
    built = spec(ALPHA)

    assert tracking_target(built, RUNTIME_COPILOT) == Path(".github") / "skills" / ALPHA
    assert tracking_target(built, RUNTIME_CLAUDE) == Path(".claude") / "skills" / ALPHA


def test_agent_file_extension_differs_between_runtimes() -> None:
    """Copilot reads <name>.agent.md and Claude reads <name>.md; one constant cannot serve both.

    Asserting the literal names rather than deriving them from the layout: deriving would restate the
    expression under test, and a wrong suffix produces a file the runtime silently never reads, with
    a successful exit and nothing to see.
    """
    built = agent(ALPHA)

    assert tracking_target(built, RUNTIME_COPILOT) == Path(".github") / "agents" / f"{ALPHA}.agent.md"
    assert tracking_target(built, RUNTIME_CLAUDE) == Path(".claude") / "agents" / f"{ALPHA}.md"


def test_agent_is_written_to_its_own_file_not_into_a_folder() -> None:
    """An agent's single rendered document lands at the file path, whatever key it was rendered under."""
    targets = item_targets(agent(ALPHA), RUNTIME_CLAUDE, {"ignored": AGENT_BODY})

    assert targets == {Path(".claude") / "agents" / f"{ALPHA}.md": AGENT_BODY}


def test_skill_files_keep_their_own_names_inside_the_folder() -> None:
    """A skill's rendered keys are real file names; an agent's is not."""
    targets = item_targets(spec(ALPHA), RUNTIME_CLAUDE, {SKILL_FILE: "a", REFERENCE_FILE: "b"})

    assert targets == {
        Path(".claude") / "skills" / ALPHA / SKILL_FILE: "a",
        Path(".claude") / "skills" / ALPHA / REFERENCE_FILE: "b",
    }


def test_a_single_file_item_rendering_several_files_is_a_bug() -> None:
    """A multi-file renderer paired with the agent kind has nowhere to put the rest.

    Reported rather than silently truncated: dropping the extra files would install an agent missing
    part of what it was built from, with a successful exit and no way to notice.
    """
    with pytest.raises(InternalStateError, match=ALPHA):
        item_targets(agent(ALPHA), RUNTIME_CLAUDE, {"a": "1", "b": "2"})


def test_every_runtime_has_a_root_and_a_label() -> None:
    """A runtime missing either would raise only once someone selected it."""
    from mega_snake.docs_gen.item_registry import RUNTIME_LABEL, RUNTIME_ROOT

    for runtime in ALL_RUNTIMES:
        assert runtime in RUNTIME_ROOT, f"{runtime!r} has no root directory"
        assert runtime in RUNTIME_LABEL, f"{runtime!r} has no human label"


def test_every_single_file_kind_declares_a_suffix_per_runtime() -> None:
    """A kind that is one file needs a name for that file in every runtime it can be installed to."""
    for kind, layout in ITEM_LAYOUT.items():
        if layout.own_directory:
            continue
        for runtime in ALL_RUNTIMES:
            assert runtime in layout.file_suffix, f"{kind!r} has no file suffix for {runtime!r}"


# ---------------------------------------------------------------------------
# Hidden items
# ---------------------------------------------------------------------------


def test_a_hidden_item_is_not_offered_but_is_still_addressable() -> None:
    """Hidden keeps an item out of the list, never out of reach.

    Both halves matter: dropping it from the offered names is the feature, and keeping it in the
    addressable names is what leaves it a way to be refreshed without reinstalling its parent.
    """
    with patch(
        "mega_snake.docs_gen.item_registry.catalogue",
        return_value={ALPHA: spec(ALPHA), BETA: agent(BETA, hidden=True)},
    ):
        offered = selectable_names()
        addressable = item_names()

    assert offered == [ALPHA], f"a hidden item was offered: {offered}"
    assert addressable == [ALPHA, BETA], f"a hidden item became unaddressable: {addressable}"


def test_a_hidden_item_is_still_installed_as_a_dependency() -> None:
    """Being hidden changes what is offered, never what a dependency resolves to."""
    catalogue = registry_of(spec(ALPHA, requires=(BETA,)), agent(BETA, hidden=True))

    assert expand_items([ALPHA], catalogue) == [ALPHA, BETA]
    assert required_by([ALPHA], catalogue) == {BETA: [ALPHA]}


def test_bundled_with_lists_what_arrives_alongside_an_item() -> None:
    """The selection list needs the forward view: what comes with this, before choosing it."""
    catalogue = registry_of(spec(ALPHA), spec(BETA), agent(GAMMA, requires=(ALPHA, BETA)))

    assert bundled_with(GAMMA, catalogue) == [ALPHA, BETA]


def test_bundled_with_excludes_the_item_itself() -> None:
    """Listing the item among its own bundle would read as installing it twice."""
    catalogue = registry_of(spec(ALPHA), spec(BETA, requires=(ALPHA,)))

    assert bundled_with(BETA, catalogue) == [ALPHA]
    assert bundled_with(ALPHA, catalogue) == []
