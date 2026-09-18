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
from mega_snake.util.formatting import InternalStateError, UserDeclinedError
from mega_snake.util.util import cli_metadata


def test_the_wrapper_runs_before_the_command_and_the_command_keeps_its_aliases() -> None:
    """The module wrapper writes the context the command then reads, and wrapping costs no alias."""

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
    assert exit_code == 21, "the command did not see what the wrapper wrote before it"
    assert getattr(wrapped_command, "aliases") == ["tc", "testcmd"], "the rebuild dropped the aliases"


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
    assert "child ran" in result.output.splitlines(), result.output


def rebuilt_command_callback() -> None:
    """Stand in for a real command callback, so the rebuild has one to carry."""


def rebuilt_result_callback(result: object, **_params: object) -> str:
    """Stand in for a group's own result callback."""
    return f"collected:{result}"


def command_settings() -> dict[str, Any]:
    """Build every named argument `click.Command.__init__` takes, each differing from its default.

    A builder rather than a module-level literal: click stores `commands` and `params` by reference
    (`self.commands = commands`), so a shared mapping would be handed to every command a test
    builds, and one test registering a subcommand would change what another one is looking at.

    Parameters:
        None

    Raises:
        None

    Returns:
        dict[str, Any]: The constructor arguments, freshly built.
    """
    return {
        "name": "parent",
        "context_settings": {"help_option_names": ["-h", "--help"], "max_content_width": 99},
        "callback": rebuilt_command_callback,
        "params": [click.Option(["--flag"], is_flag=True)],
        "help": "Parent group.",
        "epilog": "Epilogue.",
        "short_help": "Parent.",
        "options_metavar": "<OPTS>",
        "add_help_option": False,
        # A leaf command defaults to False here, while a group defaults to True, so each side needs
        # the opposite value to differ from its own default.
        "no_args_is_help": True,
        "hidden": True,
        "deprecated": True,
    }


def group_settings() -> dict[str, Any]:
    """Build the same, for what `click.Group.__init__` adds on top.

    Parameters:
        None

    Raises:
        None

    Returns:
        dict[str, Any]: The constructor arguments a group adds, freshly built.
    """
    return {
        **command_settings(),
        "no_args_is_help": False,
        "commands": {"child": click.Command(name="child")},
        "invoke_without_command": True,
        "subcommand_metavar": "<THING>",
        "chain": True,
        "result_callback": rebuilt_result_callback,
    }


# `result_callback` is the *decorator* that registers one; the callback itself lives here.
ATTRIBUTE_OF_ARGUMENT: dict[str, str] = {"result_callback": "_result_callback"}


def declared_arguments(command_class: type) -> set[str]:
    """Return every named argument a command class' own ``__init__`` accepts.

    Parameters:
        command_class: The class to read.

    Raises:
        None

    Returns:
        set[str]: The argument names, without ``self``, ``*args`` and ``**kwargs``.
    """
    return {
        name
        for name, parameter in inspect.signature(command_class.__init__).parameters.items()
        if name != "self" and parameter.kind not in (parameter.VAR_KEYWORD, parameter.VAR_POSITIONAL)
    }


@pytest.mark.parametrize(
    "command_class, declares, build_settings",
    [
        (click.Command, click.Command, command_settings),
        (CliGroup, click.Group, group_settings),
    ],
    ids=["command", "group"],
)
def test_the_rebuild_keeps_every_constructor_argument_it_was_given(
    command_class: type, declares: type, build_settings: Callable[[], dict[str, Any]]
) -> None:
    """Wrapping copies a command through its constructor, and every argument has to survive that copy.

    Fixing `commands` by name left `invoke_without_command`, `chain`, `subcommand_metavar` and
    `result_callback` behind, and each fails the same silent way -- nothing raises, the group simply
    stops behaving as declared until someone happens to invoke it the right way. `context_settings`
    is the sharpest of them: it carries `help_option_names`, so losing it publishes a CLI whose help
    flag is not the one the user has (§3.7).

    The arguments are **derived from the signature** and each is given a value that differs from its
    default, so a new argument in a future click release fails this test until someone gives it one,
    and a dropped argument fails by comparison instead of by a `hasattr` that is true either way.

    `CliGroup` is the class under test on purpose: its `__init__` is `(*args, **kwargs)`, so reading
    one signature yields nothing at all and the rebuild produces an empty group. Only a walk of the
    MRO answers, and using a plain `click.Group` here would hide that.
    """

    def wrapper(_ctx: click.Context, *_args, **_kwargs) -> None:
        """No-op pre-flight."""

    # `CliGroup.__init__` is `(*args, **kwargs)`, so the arguments it accepts are its base class'.
    settings: dict[str, Any] = build_settings()
    declared: set[str] = declared_arguments(click.Command) | declared_arguments(declares)
    assert set(settings) == declared, f"{command_class.__name__} arguments not covered: {declared ^ set(settings)}"
    original = command_class(**settings)
    default = command_class(name="parent")

    wrapped = wrapper_decorator(wrapper)(original)

    assert isinstance(wrapped, command_class)
    # The callback is the one argument the wrapping *must* change: it is what runs the module
    # wrapper before the command.
    assert wrapped.callback is not settings["callback"], "the wrapper never took over the callback"
    for argument, expected in settings.items():
        if argument == "callback":
            continue
        attribute = ATTRIBUTE_OF_ARGUMENT.get(argument, argument)
        if argument != "name":
            assert expected != getattr(default, attribute, None), f"'{argument}' was left at its default value"
        assert getattr(wrapped, attribute, None) == expected, f"the rebuild lost '{argument}'"


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


# Explicit ids: `repr(object())` carries a memory address, which changes on every run, so a node id
# built from it cannot be re-run -- not from an IDE, not with `--last-failed`.
@pytest.mark.parametrize(
    "result", [[True], {"blocked": True}, b"yes", object()], ids=["list", "dict", "bytes", "object"]
)
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
        f"Context command 'guarded' is annotated to return {annotation!r}, "
        f"which is not a primitive ({PRIMITIVE_NAMES})."
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

    return group


def register_like_the_entry_point(
    group: CliGroup, wrapper: Callable, ending: Callable, aliases: Optional[list[str]] = None
) -> CliGroup:
    """Register a group on a module, then on a root, exactly as `__main__` does.

    Going through `add_command_with_alias` and then wrapping **every** command the module declares is
    what exercises the hidden alias commands: they are separate objects carrying the same callback,
    so a decorator that judges a command by its class sees a different thing for `crew` and for `cr`.

    Parameters:
        group: The module's command group.
        wrapper: The module wrapper.
        ending: The module ending.
        aliases: The aliases to register the group under.

    Raises:
        None

    Returns:
        CliGroup: The root group, holding every wrapped command.
    """

    module_group = CliGroup(name="module")
    module_group.add_command_with_alias(group, aliases or [])
    registration = ModuleRegistration(module_group, add_context_wrapper=wrapper_context_decorator(wrapper, ending))
    root = CliGroup(name="root")
    for command in module_group.commands.values():
        root.add_command(registration.wrap(command))
    return root


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


def test_a_wrapped_context_group_keeps_its_subcommands_and_metadata() -> None:
    """Wrapping a group for its results must not cost it anything the plain rebuild keeps."""
    wrapper, ending = recording_pair([])
    group = build_context_group()
    setattr(group, "aliases", ["cr"])

    wrapped = wrapper_context_decorator(wrapper, ending)(group)

    assert isinstance(wrapped, click.Group)
    assert set(wrapped.commands) == {"verdict", "count"}
    assert getattr(wrapped, "aliases") == ["cr"]
    assert getattr(wrapped.callback, ATTR_METADATA)["flags"] == {"skip"}
    assert is_context_command(wrapped)


@pytest.mark.parametrize("name", ["crew", "cr"], ids=["real-name", "alias"])
def test_a_context_group_reaches_its_ending_under_every_name_it_is_registered_with(name: str) -> None:
    """An alias is a separate command object carrying the same callback, and it has to behave the same.

    Registered as a leaf command, an alias of a context group stops resolving its subcommands and
    hands the ending whatever the group's own callback returned -- a result no subcommand produced,
    with nothing raised and a successful exit.
    """
    calls: list[str] = []
    wrapper, ending = recording_pair(calls)
    root = register_like_the_entry_point(build_context_group(calls), wrapper, ending, aliases=["cr"])

    obj: dict[str, Any] = {}
    returned = CliRunner().invoke(root, [name, "verdict"], obj=obj, standalone_mode=False)

    assert returned.exception is None, f"'{name} verdict' failed: {returned.exception!r}"
    assert calls == ["wrapper", "group", "verdict", "ending:True"], name
    assert obj["exit_code"] == 2


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
    returned = CliRunner().invoke(wrapped, ["count"], obj={}, standalone_mode=False)

    assert returned.exception is None, returned.exception
    assert calls == ["wrapper", "group", "count", "ending:7"]


# ---------------------------------------------------------------------------
# When the module wrapper or the ending fails
# ---------------------------------------------------------------------------


def failing_pair(calls: list[str], failure: Exception) -> tuple[Callable, Callable]:
    """Return a module wrapper that fails before the command runs, and an ending that records itself.

    Parameters:
        calls: The shared call log.
        failure: What the wrapper raises.

    Raises:
        None

    Returns:
        tuple[Callable, Callable]: The failing wrapper and the ending.
    """

    def wrapper(_ctx: click.Context, *_args: Any, **_kwargs: Any) -> None:
        calls.append("wrapper")
        raise failure

    def ending(ctx: click.Context, result: Any) -> None:
        calls.append(f"ending:{result!r}")
        ctx.obj["exit_code"] = 2

    return wrapper, ending


def test_a_failing_module_wrapper_stops_a_plain_command_before_it_runs() -> None:
    """A pre-flight that refuses -- a declined working path, say -- must not let the command run anyway."""
    calls: list[str] = []
    failure = UserDeclinedError("Cannot continue without the 'workspace_temp' folder.")
    wrapper, _ending = failing_pair(calls, failure)

    @click.command(name="plain")
    def plain() -> None:
        """Ordinary command."""
        calls.append("command")

    returned = CliRunner().invoke(wrapper_decorator(wrapper)(plain), obj={}, standalone_mode=False)

    assert returned.exception is failure, repr(returned.exception)
    assert calls == ["wrapper"], "the command ran although its pre-flight refused"


def test_a_failing_module_wrapper_stops_a_context_command_and_its_ending() -> None:
    """With nothing invoked there is no result, so nothing may be written to the context either."""
    calls: list[str] = []
    failure = UserDeclinedError("Cannot continue without the 'workspace_temp' folder.")
    wrapper, ending = failing_pair(calls, failure)
    wrapped = wrapper_context_decorator(wrapper, ending)(build_context_command(calls=calls))

    obj: dict[str, Any] = {}
    returned = CliRunner().invoke(wrapped, obj=obj, standalone_mode=False)

    assert returned.exception is failure, repr(returned.exception)
    assert calls == ["wrapper"], "the command or the ending ran although the pre-flight refused"
    assert "exit_code" not in obj


def test_a_failing_module_wrapper_stops_a_context_group_before_its_subcommand() -> None:
    """The group's own callback, its subcommand and the ending all sit behind the same pre-flight."""
    calls: list[str] = []
    failure = UserDeclinedError("Cannot continue without the 'workspace_temp' folder.")
    wrapper, ending = failing_pair(calls, failure)
    wrapped = wrapper_context_decorator(wrapper, ending)(build_context_group(calls))

    obj: dict[str, Any] = {}
    returned = CliRunner().invoke(wrapped, ["verdict"], obj=obj, standalone_mode=False)

    assert returned.exception is failure, repr(returned.exception)
    assert calls == ["wrapper"], "the group ran although its pre-flight refused"
    assert "exit_code" not in obj


@pytest.mark.parametrize("command_args", [None, ["verdict"]], ids=["command", "group"])
def test_a_failing_ending_propagates_instead_of_reporting_success(command_args: Optional[list[str]]) -> None:
    """An ending that cannot deliver its status must not leave the run looking like it succeeded.

    The command has already done its work and printed whatever it prints, so swallowing the failure
    here would exit 0 with the status the ending was supposed to write silently missing.
    """
    calls: list[str] = []
    failure = InternalStateError("the context is not what the ending expected")

    def wrapper(_ctx: click.Context, *_args: Any, **_kwargs: Any) -> None:
        calls.append("wrapper")

    def ending(_ctx: click.Context, result: Any) -> None:
        calls.append(f"ending:{result!r}")
        raise failure

    command = build_context_group(calls) if command_args else build_context_command(calls=calls)
    wrapped = wrapper_context_decorator(wrapper, ending)(command)

    returned = CliRunner().invoke(wrapped, command_args or [], obj={}, standalone_mode=False)

    assert returned.exception is failure, repr(returned.exception)
    assert calls[-1].startswith("ending:"), calls
