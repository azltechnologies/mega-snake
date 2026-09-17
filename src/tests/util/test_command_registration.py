"""Test cases for command_registration.py"""

import inspect
from typing import Any, Callable, Optional

import click
import pytest
from click.testing import CliRunner

from mega_snake.util.cli_group import ATTR_METADATA, META_CONTEXT_COMMAND, CliGroup
from mega_snake.util.command_registration import (
    ModuleRegistration,
    is_context_command,
    is_primitive,
    wrapper_context_decorator,
    wrapper_decorator,
)
from mega_snake.util.formatting import InternalStateError
from mega_snake.util.util import cli_metadata


def test_wrapper_decorator() -> None:
    """Test wrapper_decorator function."""

    def wrapper(ctx: click.Context, *_args, **_kwargs) -> None:
        """Wrapper for the config_environment command."""
        ctx.obj["exit_code"] = 21

    add_wrapper = wrapper_decorator(wrapper)

    exit_code: int = 0

    @click.command()
    @click.pass_context
    # This command is decorated with cli_metadata
    @cli_metadata(name="test_command", short_help="Test command", help="This is a test command")
    def test_command(ctx) -> None:
        """Test command."""
        nonlocal exit_code
        exit_code = ctx.obj.get("exit_code", 0)

    # Add aliases to the command
    setattr(test_command, "aliases", ["tc", "testcmd"])

    wrapped_command: click.Command = add_wrapper(test_command)
    runner = CliRunner()
    result = runner.invoke(wrapped_command, obj={"foo": "bar"})
    assert result.exit_code == 0
    assert result.exception is None
    assert isinstance(wrapped_command, click.Command)
    assert exit_code == 21


def test_wrapper_decorator_keeps_a_group_a_group() -> None:
    """Wrapping must not turn a `click.Group` into a leaf command.

    The rebuild copies a command through `click.Command.__init__`'s signature, which knows nothing
    about `commands`. Before this was handled, registering the nested `config` group through its
    module wrapper silently produced a command with no subcommands, so `mgsnake config get` stopped
    resolving.
    """

    def wrapper(_ctx: click.Context, *_args, **_kwargs) -> None:
        """No-op pre-flight."""

    @click.group(name="parent")
    def parent() -> None:
        """Parent group."""

    @parent.command(name="child")
    def child() -> None:
        """Child command."""
        click.echo("child ran")

    wrapped = wrapper_decorator(wrapper)(parent)

    assert isinstance(wrapped, click.Group)
    assert set(wrapped.commands) == {"child"}
    result = CliRunner().invoke(wrapped, ["child"])
    assert result.exit_code == 0
    assert "child ran" in result.output


def test_wrapper_decorator_preserves_every_group_only_constructor_argument() -> None:
    """The sibling of the test above, generalised: `commands` was never the only casualty.

    Fixing `commands` by name left `invoke_without_command`, `chain`, `subcommand_metavar` and
    `result_callback` behind, and each fails the same silent way -- nothing raises, the group simply
    stops behaving as declared until someone happens to invoke it the right way. The parameter set is
    now derived from the class, so this test walks `Group.__init__`'s own signature rather than a
    list someone has to remember to extend.

    `CliGroup` is the class under test on purpose: its `__init__` is `(*args, **kwargs)`, so reading
    one signature yields nothing at all and the rebuild produces an empty group. Only a walk of the
    MRO answers, and using a plain `click.Group` here would hide that.
    """

    def wrapper(_ctx: click.Context, *_args, **_kwargs) -> None:
        """No-op pre-flight."""

    parent = CliGroup(
        name="parent",
        invoke_without_command=True,
        chain=False,
        subcommand_metavar="<THING>",
        help="Parent group.",
    )

    @parent.command(name="child")
    def child() -> None:
        """Child command."""
        click.echo("child ran")

    @parent.result_callback()
    def collect(result: object, **_kwargs: object) -> str:
        """Mark the result so a dropped callback is visible."""
        return f"collected:{result}"

    wrapped = wrapper_decorator(wrapper)(parent)

    group_only = {
        name
        for name, parameter in inspect.signature(click.Group.__init__).parameters.items()
        if name != "self" and parameter.kind not in (parameter.VAR_KEYWORD, parameter.VAR_POSITIONAL)
    }
    dropped = [name for name in group_only if not hasattr(wrapped, name)]
    assert dropped == [], f"the rebuild dropped {dropped}"
    assert wrapped.invoke_without_command is True, "a group declared to run bare must still run bare"
    assert wrapped.subcommand_metavar == "<THING>"
    assert wrapped.chain is False
    # `result_callback` is the decorator, so the registered callback lives on the private attribute;
    # reading the public one would compare two bound methods and pass regardless.
    assert wrapped._result_callback is collect  # pylint: disable=protected-access
    assert set(wrapped.commands) == {"child"}


# ---------------------------------------------------------------------------
# wrapper_context_decorator — the module ending writes the context, never the command
# ---------------------------------------------------------------------------

PRIMITIVE_NAMES = "int, float, str, bool, NoneType"


def build_context_command(
    name: str = "guarded",
    result: object = True,
    flagged: bool = True,
    raises: Optional[Exception] = None,
    calls: Optional[list[str]] = None,
) -> click.Command:
    """Build a command declaring itself a context command, or not.

    Parameters:
        name: The command name.
        result: What the callback returns, primitive or not.
        flagged: Whether the callback carries ``context_command=True``.
        raises: An exception the callback raises instead of returning.
        calls: A list the callback appends its own name to when it runs.

    Raises:
        None

    Returns:
        click.Command: The command, annotated to return ``bool``.
    """

    @click.command(name=name)
    @cli_metadata(context_command=flagged, flags={"no_init"})
    def command() -> bool:
        """Context command double."""
        if calls is not None:
            calls.append("command")
        if raises is not None:
            raise raises
        return result  # type: ignore[return-value]

    setattr(command, "aliases", ["gd"])
    return command


def recording_pair(calls: list[str]) -> tuple[Callable, Callable]:
    """Return a module wrapper and ending that record their calls and what the ending received.

    Parameters:
        calls: The shared call log.

    Raises:
        None

    Returns:
        tuple[Callable, Callable]: The wrapper and the ending.
    """

    @cli_metadata(flags={"skip"}, docs_group="Guards")
    def wrapper(_ctx: click.Context, *_args: Any, **_kwargs: Any) -> None:
        calls.append("wrapper")

    def ending(ctx: click.Context, result: Any) -> None:
        calls.append(f"ending:{result!r}")
        ctx.obj["exit_code"] = 2 if result else 0

    return wrapper, ending


@pytest.mark.parametrize("result, expected_exit_code", [(True, 2), (False, 0)])
def test_the_context_wrapper_hands_the_result_to_the_ending_after_the_command(
    result: bool, expected_exit_code: int
) -> None:
    """The wrapper runs first, then the command, then the ending with (ctx, result); the result passes through."""
    calls: list[str] = []
    wrapper, ending = recording_pair(calls)
    wrapped = wrapper_context_decorator(wrapper, ending)(build_context_command(result=result, calls=calls))

    obj: dict[str, Any] = {}
    returned = CliRunner().invoke(wrapped, obj=obj, standalone_mode=False)

    assert returned.exception is None, returned.exception
    assert calls == ["wrapper", "command", f"ending:{result!r}"]
    assert obj["exit_code"] == expected_exit_code
    assert returned.return_value is result


def test_the_context_wrapper_keeps_metadata_and_aliases_like_the_plain_one() -> None:
    """Both decorators share the rebuild: aliases survive, the command's flags win over the wrapper's."""
    wrapper, ending = recording_pair([])
    wrapped = wrapper_context_decorator(wrapper, ending)(build_context_command())

    metadata = getattr(wrapped.callback, ATTR_METADATA)
    assert metadata["flags"] == {"no_init"}
    assert metadata["flags"] != {"skip"}
    assert metadata[META_CONTEXT_COMMAND] is True
    assert getattr(wrapped, "aliases") == ["gd"]
    assert getattr(wrapped, "docs_group") == "Guards"


def test_the_ending_never_runs_when_the_context_command_raises() -> None:
    """A failing command propagates untouched, and nothing is written to the context."""
    calls: list[str] = []
    wrapper, ending = recording_pair(calls)
    failure = ValueError("payload rejected")
    wrapped = wrapper_context_decorator(wrapper, ending)(build_context_command(raises=failure, calls=calls))

    obj: dict[str, Any] = {}
    returned = CliRunner().invoke(wrapped, obj=obj, standalone_mode=False)

    assert returned.exception is failure
    assert calls == ["wrapper", "command"]
    assert "exit_code" not in obj


@pytest.mark.parametrize("result", [[True], {"blocked": True}, b"yes", object()], ids=repr)
def test_a_context_command_returning_a_non_primitive_is_a_bug(result: object) -> None:
    """The runtime check refuses what the annotation promised against, before the ending sees it."""
    calls: list[str] = []
    wrapper, ending = recording_pair(calls)
    wrapped = wrapper_context_decorator(wrapper, ending)(build_context_command(result=result, calls=calls))

    obj: dict[str, Any] = {}
    returned = CliRunner().invoke(wrapped, obj=obj, standalone_mode=False)

    assert isinstance(returned.exception, InternalStateError), f"{result!r}: {returned.exception!r}"
    assert str(returned.exception) == (
        f"Context command 'guarded' returned {type(result).__name__}, which is not a primitive ({PRIMITIVE_NAMES})."
    )
    assert calls == ["wrapper", "command"], f"{result!r} reached the ending"
    assert "exit_code" not in obj


@pytest.mark.parametrize(
    "value, expected",
    [(0, True), (1.5, True), ("", True), (False, True), (None, True), (b"", False), ([], False), ({}, False)],
    ids=repr,
)
def test_is_primitive_accepts_exactly_the_primitive_types(value: object, expected: bool) -> None:
    """Falsy primitives are primitive; bytes and containers are not."""
    assert is_primitive(value) is expected, f"is_primitive({value!r}) should be {expected}"


@pytest.mark.parametrize("annotation", [bool, int, str, float, type(None), Optional[bool], bool | None], ids=repr)
def test_a_context_command_annotated_with_a_primitive_registers(annotation: object) -> None:
    """Every primitive, and every union of primitives, is an acceptable return annotation."""
    command = build_context_command()
    command.callback.__annotations__["return"] = annotation  # type: ignore[union-attr]
    wrapper, ending = recording_pair([])

    assert is_context_command(wrapper_context_decorator(wrapper, ending)(command)), repr(annotation)


@pytest.mark.parametrize("annotation", [list, dict[str, bool], bytes, Optional[list], object], ids=repr)
def test_a_context_command_annotated_with_a_non_primitive_is_refused_at_registration(annotation: object) -> None:
    """The annotation is checked when the module registers the command, long before it runs."""
    command = build_context_command()
    command.callback.__annotations__["return"] = annotation  # type: ignore[union-attr]
    calls: list[str] = []
    wrapper, ending = recording_pair(calls)

    with pytest.raises(InternalStateError) as raised:
        wrapper_context_decorator(wrapper, ending)(command)

    assert str(raised.value) == (
        f"Context command 'guarded' is annotated to return {annotation!r}, which is not a primitive ({PRIMITIVE_NAMES})."
    )
    assert calls == []


def test_a_context_command_without_a_return_annotation_is_refused_at_registration() -> None:
    """No annotation is no promise, so it is refused like a wrong one."""
    command = build_context_command()
    del command.callback.__annotations__["return"]  # type: ignore[union-attr]
    wrapper, ending = recording_pair([])

    with pytest.raises(InternalStateError) as raised:
        wrapper_context_decorator(wrapper, ending)(command)

    assert str(raised.value) == (
        f"Context command 'guarded' must annotate its return type with a primitive ({PRIMITIVE_NAMES})."
    )


def test_the_plain_wrapper_refuses_a_context_command() -> None:
    """A context command wrapped without an ending would silently lose its result."""
    calls: list[str] = []
    wrapper, _ending = recording_pair(calls)

    with pytest.raises(InternalStateError) as raised:
        wrapper_decorator(wrapper)(build_context_command(calls=calls))

    assert str(raised.value) == (
        "Command 'guarded' is a context command and must be registered through "
        "wrapper_context_decorator, not wrapper_decorator."
    )
    assert calls == []


def test_the_context_wrapper_refuses_an_ordinary_command() -> None:
    """An unflagged command must go through wrapper_decorator, even when its annotation is primitive."""
    calls: list[str] = []
    wrapper, ending = recording_pair(calls)
    command = build_context_command(flagged=False, calls=calls)

    assert is_context_command(command) is False
    with pytest.raises(InternalStateError) as raised:
        wrapper_context_decorator(wrapper, ending)(command)

    assert str(raised.value) == (
        "Command 'guarded' is not a context command and must be registered through "
        "wrapper_decorator, not wrapper_context_decorator."
    )
    assert calls == []


# ---------------------------------------------------------------------------
# ModuleRegistration — which decorator wraps which command
# ---------------------------------------------------------------------------


def build_module_command(name: str, context_command: bool) -> click.Command:
    """Build a command that is, or is not, a context command.

    Parameters:
        name: The command name.
        context_command: Whether the callback carries ``context_command=True``.

    Raises:
        None

    Returns:
        click.Command: The command.
    """

    def callback() -> bool:
        """Command double."""
        return True

    setattr(callback, ATTR_METADATA, {META_CONTEXT_COMMAND: context_command})
    return click.Command(name=name, callback=callback)


def tagging_decorator(tag: str) -> Callable[[click.Command], click.Command]:
    """Return a decorator that marks the command it wrapped, so the chosen one is visible.

    Parameters:
        tag: The mark to leave on the command.

    Raises:
        None

    Returns:
        Callable: The decorator.
    """

    def decorator(command: click.Command) -> click.Command:
        setattr(command, "wrapped_by", tag)
        return command

    return decorator


def test_a_module_registration_without_any_wrapper_is_a_bug() -> None:
    """A module that can wrap nothing is refused when it is declared, not when a command needs it."""
    group = CliGroup(name="orphan")

    with pytest.raises(InternalStateError) as raised:
        ModuleRegistration(group)

    assert str(raised.value) == "Module group 'orphan' is registered without add_wrapper or add_context_wrapper."


@pytest.mark.parametrize(
    "context_command, expected, other",
    [(True, "context", "plain"), (False, "plain", "context")],
)
def test_each_command_is_wrapped_by_the_decorator_its_kind_needs(
    context_command: bool, expected: str, other: str
) -> None:
    """With both decorators exported, the flag alone decides which one wraps the command."""
    registration = ModuleRegistration(
        CliGroup(name="both"),
        add_wrapper=tagging_decorator("plain"),
        add_context_wrapper=tagging_decorator("context"),
    )

    wrapped = registration.wrap(build_module_command("cmd", context_command))

    assert getattr(wrapped, "wrapped_by") == expected, f"context_command={context_command}"
    assert getattr(wrapped, "wrapped_by") != other


@pytest.mark.parametrize(
    "context_command, exported, missing",
    [(True, {"add_wrapper": tagging_decorator("plain")}, "add_context_wrapper"),
     (False, {"add_context_wrapper": tagging_decorator("context")}, "add_wrapper")],
)
def test_a_command_whose_decorator_the_module_does_not_export_is_a_bug(
    context_command: bool, exported: dict[str, Callable], missing: str
) -> None:
    """The other decorator is never used as a fallback: the command is refused, naming it and its module."""
    registration = ModuleRegistration(CliGroup(name="half"), **exported)
    command = build_module_command("lonely", context_command)

    with pytest.raises(InternalStateError) as raised:
        registration.wrap(command)

    assert str(raised.value) == (
        f"Command 'lonely' of module group 'half' needs {missing}, which the module does not export."
    )
    assert not hasattr(command, "wrapped_by"), f"{missing} missing, yet the command was wrapped"


# ---------------------------------------------------------------------------
# Context groups -- the ending receives what the invoked subcommand returned
# ---------------------------------------------------------------------------


def build_context_group(calls: Optional[list[str]] = None, **group_settings: Any) -> CliGroup:
    """Build a group flagged as a context command, with two subcommands returning different primitives.

    Parameters:
        calls: A list each callback appends its own name to when it runs.
        group_settings: Extra constructor arguments for the group (``chain``, ``invoke_without_command``).

    Raises:
        None

    Returns:
        CliGroup: The group, holding ``verdict`` (returns True) and ``count`` (returns 7).
    """
    log: list[str] = calls if calls is not None else []

    @cli_metadata(context_command=True, flags={"skip"})
    def group_callback() -> None:
        log.append("group")

    group = CliGroup(name="crew", callback=group_callback, **group_settings)

    @group.command(name="verdict")
    def verdict() -> bool:
        """Subcommand returning a bool."""
        log.append("verdict")
        return True

    @group.command(name="count")
    def count() -> int:
        """Subcommand returning an int."""
        log.append("count")
        return 7

    setattr(group, "aliases", ["cr"])
    return group


@pytest.mark.parametrize("subcommand, expected", [("verdict", True), ("count", 7)])
def test_a_context_group_hands_the_subcommand_result_to_the_ending(subcommand: str, expected: object) -> None:
    """The wrapper runs first, then the group and its subcommand, then the ending with that subcommand's value."""
    calls: list[str] = []
    wrapper, ending = recording_pair(calls)
    wrapped = wrapper_context_decorator(wrapper, ending)(build_context_group(calls))

    obj: dict[str, Any] = {}
    returned = CliRunner().invoke(wrapped, [subcommand], obj=obj, standalone_mode=False)

    assert returned.exception is None, returned.exception
    assert calls == ["wrapper", "group", subcommand, f"ending:{expected!r}"], subcommand
    assert returned.return_value == expected
    assert obj["exit_code"] == (2 if expected else 0)


def test_a_wrapped_context_group_keeps_its_subcommands_metadata_and_aliases() -> None:
    """Wrapping a group for its results must not cost it anything the plain rebuild keeps."""
    wrapper, ending = recording_pair([])
    wrapped = wrapper_context_decorator(wrapper, ending)(build_context_group())

    assert isinstance(wrapped, click.Group)
    assert set(wrapped.commands) == {"verdict", "count"}
    assert getattr(wrapped, "aliases") == ["cr"]
    assert getattr(wrapped.callback, ATTR_METADATA)["flags"] == {"skip"}
    assert is_context_command(wrapped)


def test_the_ending_never_runs_when_a_context_group_subcommand_raises() -> None:
    """A failing subcommand propagates untouched, and nothing is written to the context."""
    calls: list[str] = []
    wrapper, ending = recording_pair(calls)
    group = build_context_group(calls)
    failure = ValueError("mission state unreadable")

    @group.command(name="broken")
    def broken() -> bool:
        """Subcommand that raises."""
        calls.append("broken")
        raise failure

    wrapped = wrapper_context_decorator(wrapper, ending)(group)
    obj: dict[str, Any] = {}
    returned = CliRunner().invoke(wrapped, ["broken"], obj=obj, standalone_mode=False)

    assert returned.exception is failure
    assert calls == ["wrapper", "group", "broken"]
    assert "exit_code" not in obj


def test_a_context_group_subcommand_returning_a_non_primitive_is_a_bug() -> None:
    """The run-time check names the group and the subcommand, and stops before the ending."""
    calls: list[str] = []
    wrapper, ending = recording_pair(calls)
    group = build_context_group(calls)

    @group.command(name="action")
    def action() -> str:
        """Subcommand that breaks its own annotation."""
        return {"status": "error"}  # type: ignore[return-value]

    wrapped = wrapper_context_decorator(wrapper, ending)(group)
    obj: dict[str, Any] = {}
    returned = CliRunner().invoke(wrapped, ["action"], obj=obj, standalone_mode=False)

    assert isinstance(returned.exception, InternalStateError), repr(returned.exception)
    assert str(returned.exception) == (
        f"Context command 'crew action' returned dict, which is not a primitive ({PRIMITIVE_NAMES})."
    )
    assert not any(call.startswith("ending") for call in calls)
    assert "exit_code" not in obj


@pytest.mark.parametrize(
    "annotation, expected",
    [
        (None, f"Context command 'crew verdict' must annotate its return type with a primitive ({PRIMITIVE_NAMES})."),
        (
            dict,
            f"Context command 'crew verdict' is annotated to return {dict!r}, "
            f"which is not a primitive ({PRIMITIVE_NAMES}).",
        ),
    ],
    ids=["missing", "non-primitive"],
)
def test_every_subcommand_of_a_context_group_is_checked_at_registration(annotation: object, expected: str) -> None:
    """One subcommand without a primitive promise refuses the whole group, naming group and subcommand."""
    group = build_context_group()
    callback = group.commands["verdict"].callback
    if annotation is None:
        del callback.__annotations__["return"]  # type: ignore[union-attr]
    else:
        callback.__annotations__["return"] = annotation  # type: ignore[union-attr]
    wrapper, ending = recording_pair([])

    with pytest.raises(InternalStateError) as raised:
        wrapper_context_decorator(wrapper, ending)(group)

    assert str(raised.value) == expected


@pytest.mark.parametrize(
    "settings, declared",
    [
        ({"chain": True}, "chain=True"),
        ({"invoke_without_command": True}, "invoke_without_command=True"),
        ({"chain": True, "invoke_without_command": True}, "chain=True, invoke_without_command=True"),
    ],
    ids=["chain", "without-command", "both"],
)
def test_a_context_group_whose_results_are_not_one_primitive_is_refused(settings: dict, declared: str) -> None:
    """A chained group passes a list, and a bare invocation passes the group's own value: neither is supported."""
    wrapper, ending = recording_pair([])

    with pytest.raises(InternalStateError) as raised:
        wrapper_context_decorator(wrapper, ending)(build_context_group(**settings))

    assert str(raised.value) == (
        f"Context group 'crew' cannot hand its results to an ending: it declares {declared}."
    )


def test_a_context_group_with_its_own_result_callback_is_refused() -> None:
    """A result callback of its own would sit between the subcommand and the ending."""
    group = build_context_group()

    @group.result_callback()
    def reshape(result: object, **_params: object) -> object:
        """Transform the result before anyone else sees it."""
        return result

    wrapper, ending = recording_pair([])

    with pytest.raises(InternalStateError) as raised:
        wrapper_context_decorator(wrapper, ending)(group)

    assert str(raised.value) == (
        "Context group 'crew' cannot hand its results to an ending: it declares a result callback of its own."
    )


def test_a_context_group_holding_a_nested_group_is_refused() -> None:
    """A nested group's value is whatever its own result callback makes of it, so it is not supported."""
    group = build_context_group()
    group.add_command(CliGroup(name="inner"))
    wrapper, ending = recording_pair([])

    with pytest.raises(InternalStateError) as raised:
        wrapper_context_decorator(wrapper, ending)(group)

    assert str(raised.value) == "Context group 'crew' cannot hand its results to an ending: 'inner' is a nested group."


def test_the_plain_wrapper_refuses_a_context_group() -> None:
    """A flagged group wrapped without its ending would lose every subcommand's result."""
    wrapper, _ending = recording_pair([])

    with pytest.raises(InternalStateError) as raised:
        wrapper_decorator(wrapper)(build_context_group())

    assert str(raised.value) == (
        "Command 'crew' is a context command and must be registered through "
        "wrapper_context_decorator, not wrapper_decorator."
    )


def test_a_module_registration_wraps_a_context_group_with_its_context_decorator() -> None:
    """`wrap` decides by the flag on the group's own callback, exactly as for a leaf command."""
    calls: list[str] = []
    wrapper, ending = recording_pair(calls)
    registration = ModuleRegistration(
        CliGroup(name="module"),
        add_wrapper=wrapper_decorator(wrapper),
        add_context_wrapper=wrapper_context_decorator(wrapper, ending),
    )

    wrapped = registration.wrap(build_context_group(calls))
    CliRunner().invoke(wrapped, ["count"], obj={}, standalone_mode=False)

    assert calls == ["wrapper", "group", "count", "ending:7"]
