"""Turn each command a module declares into the command the CLI registers.

Every ``module.py`` exports one ``ModuleRegistration``: its command group plus the decorators that
wrap its commands. ``wrapper_decorator`` runs the module wrapper before a command;
``wrapper_context_decorator`` also runs a module ending after a context command, which is how a
command's outcome reaches the click context without the command ever touching it.
"""

import inspect
from dataclasses import dataclass
from types import UnionType
from typing import Any, Callable, Optional, Tuple, Union, cast, get_args, get_origin, get_type_hints

import click

from mega_snake.util.cli_group import (
    ATTR_ALIAS,
    ATTR_DOCS,
    ATTR_GROUP,
    ATTR_METADATA,
    META_CONTEXT_COMMAND,
    CliGroup,
)
from mega_snake.util.formatting import InternalStateError


# `Group.result_callback` is the *decorator* that registers one; the registered callback itself is
# stored under this name. Reading the public attribute would pass a bound method as the callback.
_CONSTRUCTOR_ATTRIBUTE_OVERRIDES: dict[str, str] = {"result_callback": "_result_callback"}


def _constructor_parameters(command_class: type) -> set[str]:
    """Return every named constructor parameter a command class accepts, across its whole MRO.

    The walk is the point. ``CliGroup.__init__`` is ``(*args, **kwargs)`` forwarding to its base, so
    reading that one signature yields nothing at all and the rebuild silently produces a group with
    no subcommands -- the exact failure this function exists to prevent, reintroduced one level up.
    ``**kwargs`` and ``*args`` are excluded for the same reason they are useless here: they are the
    funnel, not settings, and passing one by name would raise.

    Parameters:
        command_class: The class whose constructors to read.

    Raises:
        None

    Returns:
        set[str]: The parameter names that can be passed by keyword.
    """
    variadic = (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
    names: set[str] = set()
    for ancestor in command_class.__mro__:
        if not (isinstance(ancestor, type) and issubclass(ancestor, click.Command)):
            continue
        names |= {
            name
            for name, parameter in inspect.signature(ancestor.__init__).parameters.items()
            if name != "self" and parameter.kind not in variadic
        }
    return names


def _constructor_argument(command: click.Command, name: str) -> Any:
    """Read the value a rebuilt command should receive for one constructor parameter.

    Parameters:
        command: The command being copied.
        name: The constructor parameter name.

    Raises:
        None

    Returns:
        Any: The stored value, read from the private attribute when the public one is not it.
    """
    return getattr(command, _CONSTRUCTOR_ATTRIBUTE_OVERRIDES.get(name, name))


def _has_argument(command: click.Command, name: str) -> bool:
    """Report whether a command carries a value for one constructor parameter.

    Parameters:
        command: The command being copied.
        name: The constructor parameter name.

    Raises:
        None

    Returns:
        bool: True when the attribute the rebuild would read exists.
    """
    return hasattr(command, _CONSTRUCTOR_ATTRIBUTE_OVERRIDES.get(name, name))


def _rebuild_command(command: click.Command) -> click.Command:
    """Rebuild a command as the same class, so wrapping it cannot change what it is.

    Wrapping copies the command through ``click.Command.__init__``'s signature, which is the reason
    §2.3 of the contributor guide insists custom attributes be re-applied by hand afterwards. A
    subclass constructor accepts more than that signature mentions, and everything it adds is
    dropped unless it is copied too: a ``click.Group`` rebuilt through the plain ``Command``
    constructor comes out a leaf command with no subcommands, so ``mgsnake config get`` stops
    resolving the moment the group is registered through a module wrapper like every other command.

    The parameter set is therefore taken from **the command's own class** as well as from
    ``click.Command``, rather than naming the extras one by one. Enumerating them fixed ``commands``
    and left ``invoke_without_command``, ``chain``, ``result_callback`` and ``subcommand_metavar``
    behind, each of which fails the same silent way -- a group declared
    ``@click.group(invoke_without_command=True)`` would simply stop running its own body, with
    nothing to see until someone invoked it bare. Deriving the set means the next subclass, or the
    next click release, is covered without anyone remembering to come back here.

    Parameters:
        command: The command (or group) to copy.

    Raises:
        None

    Returns:
        click.Command: A fresh instance of the same class carrying the same constructor arguments.
    """
    attribute_names: set[str] = _constructor_parameters(click.Command) | _constructor_parameters(type(command))
    return type(command)(
        **{name: _constructor_argument(command, name) for name in attribute_names if _has_argument(command, name)}
    )


# Custom attributes `_rebuild_command` cannot see, re-applied onto every wrapped command by hand.
PRESERVED_ATTRS: Tuple[str, ...] = (ATTR_ALIAS, ATTR_DOCS, ATTR_GROUP)

# What a context command may return. A module ending reads the result only to decide what to write
# into the click context, so anything richer is a sign the command is handing it work to do.
# `bytes` is left out on purpose: no ending has a reason to branch on raw data.
PRIMITIVE_TYPES: Tuple[type, ...] = (int, float, str, bool, type(None))
_PRIMITIVE_NAMES: str = ", ".join(primitive.__name__ for primitive in PRIMITIVE_TYPES)


def is_primitive(value: Any) -> bool:
    """Report whether a value is one a context command is allowed to return.

    Parameters:
        value: The value to classify.

    Raises:
        None

    Returns:
        bool: True for ``int``, ``float``, ``str``, ``bool`` and ``None``; False otherwise.
    """
    return isinstance(value, PRIMITIVE_TYPES)


def is_context_command(command: click.Command) -> bool:
    """Report whether a command declared ``@cli_metadata(context_command=True)``.

    Parameters:
        command: The command to inspect.

    Raises:
        None

    Returns:
        bool: True when the command callback carries the flag.
    """
    return bool(getattr(command.callback, ATTR_METADATA, {}).get(META_CONTEXT_COMMAND, False))


def _is_primitive_annotation(annotation: Any) -> bool:
    """Report whether a return annotation only admits primitive values.

    ``Optional[bool]`` and ``bool | None`` are accepted, since every member of the union is.

    Parameters:
        annotation: The resolved return annotation.

    Raises:
        None

    Returns:
        bool: True when the annotation, or every member of its union, is in ``PRIMITIVE_TYPES``.
    """
    members = get_args(annotation) if get_origin(annotation) in (Union, UnionType) else (annotation,)
    return all(member in PRIMITIVE_TYPES for member in members)


def _require_primitive_return_annotation(callback: Optional[Callable], label: str) -> None:
    """Refuse a context callback that does not promise a primitive return value.

    Parameters:
        callback: The callback whose return value reaches a module ending.
        label: How the command is named in the refusal: its name, or the group and subcommand names.

    Raises:
        InternalStateError: If the callback has no return annotation, or it is not primitive.

    Returns:
        None
    """
    hints: dict[str, Any] = get_type_hints(callback) if callback else {}
    if "return" not in hints:
        raise InternalStateError(
            f"Context command '{label}' must annotate its return type with a primitive ({_PRIMITIVE_NAMES})."
        )
    if not _is_primitive_annotation(hints["return"]):
        raise InternalStateError(
            f"Context command '{label}' is annotated to return {hints['return']!r}, "
            f"which is not a primitive ({_PRIMITIVE_NAMES})."
        )


def _require_context_group_shape(group: click.Group) -> None:
    """Refuse a context group whose subcommand results could not reach an ending one by one.

    A context group hands the ending the value its subcommand returned, through the group's result
    callback. That only means one primitive per invocation for a plain group of leaf commands, so
    every other shape is refused rather than half supported: a chained group passes a list, a group
    invoked without a subcommand passes its own callback's value, a nested group passes whatever its
    own result callback makes of it, and an existing result callback would sit between the
    subcommand and the ending.

    Parameters:
        group: The context group being registered.

    Raises:
        InternalStateError: If the group is chained, runs without a subcommand, already has a result
            callback, holds a nested group, or has a subcommand not annotated with a primitive.

    Returns:
        None
    """
    unsupported: list[str] = []
    if group.chain:
        unsupported.append("chain=True")
    if group.invoke_without_command:
        unsupported.append("invoke_without_command=True")
    if group._result_callback is not None:  # pylint: disable=protected-access
        unsupported.append("a result callback of its own")
    if unsupported:
        raise InternalStateError(
            f"Context group '{group.name}' cannot hand its results to an ending: it declares {', '.join(unsupported)}."
        )
    for name, subcommand in group.commands.items():
        if isinstance(subcommand, click.Group):
            raise InternalStateError(
                f"Context group '{group.name}' cannot hand its results to an ending: '{name}' is a nested group."
            )
        _require_primitive_return_annotation(subcommand.callback, f"{group.name} {name}")


def _deliver(ending: Callable[[click.Context, Any], None], ctx: click.Context, label: str, result: Any) -> Any:
    """Hand a context command's result to its module ending, once it is known to be primitive.

    Parameters:
        ending: The module ending.
        ctx: The click context the ending writes into.
        label: How the command is named if the result is refused.
        result: What the command returned.

    Raises:
        InternalStateError: If the result is not a primitive.

    Returns:
        Any: The result, untouched.
    """
    if not is_primitive(result):
        raise InternalStateError(
            f"Context command '{label}' returned {type(result).__name__}, "
            f"which is not a primitive ({_PRIMITIVE_NAMES})."
        )
    ending(ctx, result)
    return result


def _merge_metadata(target: Callable, source: Any) -> None:
    """Merge the ``@cli_metadata`` of a wrapper or callback into the new callback.

    Called for the module wrapper first and the command callback second, so a per-command key wins.

    Parameters:
        target: The callback that replaces the command's own.
        source: The module wrapper or the original callback.

    Raises:
        None

    Returns:
        None
    """
    if source_metadata := getattr(source, ATTR_METADATA, {}):
        if not hasattr(target, ATTR_METADATA):
            setattr(target, ATTR_METADATA, {})
        getattr(target, ATTR_METADATA).update(source_metadata)


def _apply_command_metadata(target: click.Command, source: Any) -> None:
    """Copy custom documentation metadata from a wrapper or callback onto a command.

    Parameters:
        target: The command that should receive the metadata.
        source: The callback or wrapper that may carry metadata.

    Raises:
        None

    Returns:
        None
    """
    metadata: dict[str, Any] = getattr(source, ATTR_METADATA, {})
    for attr_name in (ATTR_DOCS, ATTR_GROUP):
        if value := metadata.get(attr_name):
            setattr(target, attr_name, value)


def _wrap_command(command: click.Command, sub_wrapper: Callable, callback: Callable) -> click.Command:
    """Rebuild a command around a new callback, keeping everything the rebuild would drop.

    Parameters:
        command: The original command.
        sub_wrapper: The module wrapper whose metadata applies to the command.
        callback: The callback that replaces the command's own.

    Raises:
        None

    Returns:
        click.Command: The rebuilt command, invoking ``callback``.
    """
    _merge_metadata(callback, sub_wrapper)
    _merge_metadata(callback, command.callback)

    comm = _rebuild_command(command)
    comm.callback = callback
    for attr_name in PRESERVED_ATTRS:
        if value := getattr(command, attr_name, None):
            setattr(comm, attr_name, value)
    _apply_command_metadata(comm, sub_wrapper)
    _apply_command_metadata(comm, command.callback)
    return comm


def wrapper_decorator(sub_wrapper: Callable) -> Callable:
    """Build the decorator that runs a module wrapper before each of its commands.

    Parameters:
        sub_wrapper: The module wrapper, called with the click context and the command arguments.

    Raises:
        None

    Returns:
        Callable: A decorator turning a command into its wrapped copy.
    """

    def decorator(command: click.Command) -> click.Command:
        """Wrap one command with the module wrapper.

        Parameters:
            command: The command (or group) to wrap.

        Raises:
            InternalStateError: If the command is a context command, which needs
                ``wrapper_context_decorator`` instead.

        Returns:
            click.Command: The wrapped command.
        """
        if is_context_command(command):
            raise InternalStateError(
                f"Command '{command.name}' is a context command and must be registered through "
                "wrapper_context_decorator, not wrapper_decorator."
            )

        @click.pass_context
        def wrapper(ctx, *args, **kwargs) -> None:
            sub_wrapper(ctx, *args, **kwargs)
            return ctx.invoke(command, *args, **kwargs)

        return _wrap_command(command, sub_wrapper, wrapper)

    return decorator


def wrapper_context_decorator(sub_wrapper: Callable, ending: Callable[[click.Context, Any], None]) -> Callable:
    """Build the decorator for context commands: a module wrapper before, a module ending after.

    Commands never touch the click context; the module layer does. A command whose outcome has to
    reach the context (an exit status, say) declares ``@cli_metadata(context_command=True)``,
    returns a primitive, and lets its module's ``ending`` translate that result into the context.

    A **group** may be a context command too. Its callback runs before the subcommand, so the value
    worth delivering is the subcommand's: the ending is attached as the group's result callback and
    receives what the invoked subcommand returned. Every subcommand must then annotate a primitive
    return, and the group must be a plain group of leaf commands (see
    ``_require_context_group_shape``).

    Parameters:
        sub_wrapper: The module wrapper, called with the click context and the command arguments.
        ending: Called with the click context and the command result once the command returned.

    Raises:
        None

    Returns:
        Callable: A decorator turning a context command into its wrapped copy.
    """

    def decorator(command: click.Command) -> click.Command:
        """Wrap one context command, or context group, with the module wrapper and ending.

        Parameters:
            command: The context command or group to wrap.

        Raises:
            InternalStateError: If the command is not flagged as a context command, a leaf callback
                or a group's subcommand does not annotate a primitive return type, or the group has
                a shape whose results cannot reach an ending one by one.

        Returns:
            click.Command: The wrapped command.
        """
        if not is_context_command(command):
            raise InternalStateError(
                f"Command '{command.name}' is not a context command and must be registered through "
                "wrapper_decorator, not wrapper_context_decorator."
            )
        if isinstance(command, click.Group):
            return _wrap_context_group(command, sub_wrapper, ending)
        _require_primitive_return_annotation(command.callback, str(command.name))

        @click.pass_context
        def wrapper(ctx, *args, **kwargs) -> Any:
            sub_wrapper(ctx, *args, **kwargs)
            return _deliver(ending, ctx, str(command.name), ctx.invoke(command, *args, **kwargs))

        return _wrap_command(command, sub_wrapper, wrapper)

    return decorator


def _wrap_context_group(
    group: click.Group, sub_wrapper: Callable, ending: Callable[[click.Context, Any], None]
) -> click.Command:
    """Wrap a context group: the module wrapper before its callback, the ending on its subcommand's result.

    Parameters:
        group: The context group.
        sub_wrapper: The module wrapper.
        ending: The module ending.

    Raises:
        InternalStateError: If the group's shape or a subcommand's annotation is refused.

    Returns:
        click.Command: The wrapped group, carrying the ending as its result callback.
    """
    _require_context_group_shape(group)

    @click.pass_context
    def wrapper(ctx, *args, **kwargs) -> Any:
        sub_wrapper(ctx, *args, **kwargs)
        return ctx.invoke(group, *args, **kwargs)

    wrapped = _wrap_command(group, sub_wrapper, wrapper)

    def deliver_subcommand_result(result: Any, **_params: Any) -> Any:
        ctx = click.get_current_context()
        return _deliver(ending, ctx, f"{group.name} {ctx.invoked_subcommand}", result)

    # The rebuild keeps the class, so the copy of a group is a group.
    rebuilt = cast(click.Group, wrapped)
    rebuilt.result_callback()(deliver_subcommand_result)
    return rebuilt


@dataclass(frozen=True)
class ModuleRegistration:
    """One module's command group, and the decorators that wrap its commands.

    Every ``module.py`` exports exactly one, named ``registration``, built from its command group and
    the decorators it needs: ``add_wrapper`` for its ordinary commands, ``add_context_wrapper`` for its
    context commands (``@cli_metadata(context_command=True)``), or both. The CLI entry point wraps
    each command of the group through ``wrap``.

    Parameters:
        group: The module command group.
        add_wrapper: The decorator built by ``wrapper_decorator``, if the module has one.
        add_context_wrapper: The decorator built by ``wrapper_context_decorator``, if the module has one.
    """

    group: CliGroup
    add_wrapper: Optional[Callable] = None
    add_context_wrapper: Optional[Callable] = None

    def __post_init__(self) -> None:
        """Refuse a registration that could wrap nothing.

        Parameters:
            None

        Raises:
            InternalStateError: If neither decorator was given.

        Returns:
            None
        """
        if self.add_wrapper is None and self.add_context_wrapper is None:
            raise InternalStateError(
                f"Module group '{self.group.name}' is registered without add_wrapper or add_context_wrapper."
            )

    def wrap(self, command: click.Command) -> click.Command:
        """Wrap one command of the module with the decorator its kind needs.

        Parameters:
            command: A command of this module's group.

        Raises:
            InternalStateError: If the module does not export the decorator the command needs.

        Returns:
            click.Command: The wrapped command.
        """
        if is_context_command(command):
            decorator, name = self.add_context_wrapper, "add_context_wrapper"
        else:
            decorator, name = self.add_wrapper, "add_wrapper"
        if decorator is None:
            raise InternalStateError(
                f"Command '{command.name}' of module group '{self.group.name}' needs {name}, "
                "which the module does not export."
            )
        return decorator(command)
