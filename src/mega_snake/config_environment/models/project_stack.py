"""This module contains the model describing the technology stacks a workspace can be configured for.

The workspace configuration used to be Java-centric: `working-env` always offered a Java version and
always wrote the Java/Gradle tasks, launch configurations and extensions, even on a repository that
holds no JVM code at all. `ProjectStack` turns that into data: every stack knows the marker files
that reveal its presence in the repository, plus the VS Code artifacts that only make sense when the
stack is part of the workspace. Everything the workspace generator emits is tagged with the stack it
belongs to, so a stack that is not active simply contributes nothing.
"""

from enum import Enum
from functools import lru_cache
import os
from typing import AbstractSet, Callable, Iterable, Mapping, Optional, Protocol, TypeVar

ALL_STACKS: str = "all"

# Marker that switches the opt-in development stack on; see ProjectStack.SNAKE.
SNAKE_MARKER: str = ".mgsnake-dev"

# Explicitly typed empty values: an inline `()`/`[]`/`{}` inside an enum member tuple leaves the
# member's type unresolved for the type checker. The mutable ones are shared by identity across
# every member that uses them, which is why `__init__` copies them instead of storing them as-is.
NO_MARKERS: tuple[str, ...] = ()
NO_IMPLIED: tuple[str, ...] = ()
NO_EXTENSIONS: list[str] = []
NO_ASSOCIATIONS: dict[str, str] = {}


class ProjectStack(Enum):
    """A technology stack the VS Code workspace can be configured for.

    Attributes:
        key: The lowercase name used by the `--stack` option and in user-facing messages.
        markers: File names whose presence in the repository root activates the stack.
        implied_keys: Keys of the stacks this one drags along (a build tool needs its language).
        extensions: Recommended VS Code extensions contributed by the stack.
        file_associations: `files.associations` entries contributed by the stack.
        description: Short explanation shown when the stack list is reported to the user.
        opt_in: Whether the stack is reachable only through its marker file. An opt-in stack is
            absent from `--stack` and from `all`, so it never reaches a repository that did not
            explicitly ask for it by dropping the marker in its root.
    """

    COMMON = (
        "common",
        NO_MARKERS,
        NO_IMPLIED,
        [
            # Recommended for every stack even though the input it powers (`TODAY_TIMESTAMP`) is only
            # written when a task or a launch configuration survives the stack filter. Moving it
            # would mean duplicating it on every stack that has one, and an unused recommendation is
            # a one-line prompt VS Code shows once -- cheaper than the duplication.
            "augustocdias.tasks-shell-input",
            "berublan.vscode-log-viewer",
            "bradzacher.vscode-copy-filename",
            "github.vscode-github-actions",
            "github.vscode-pull-request-github",
            "graphql.vscode-graphql-syntax",
            "graphql.vscode-graphql",
            "letmaik.git-tree-compare",
            "mhutchie.git-graph",
            "natqe.reload",
            "sandcastle.vscode-open",
            "solomonkinard.git-blame",
        ],
        {"**/.github/workflows/*.yml": "github-actions-workflow", "*.yml": "yaml"},
        "editor, git and log-viewer configuration shared by every project",
    )
    JAVA = (
        "java",
        NO_MARKERS,
        NO_IMPLIED,
        ["vscjava.vscode-java-pack"],
        NO_ASSOCIATIONS,
        "Java runtimes, formatter and remote debugging",
    )
    GRADLE = (
        "gradle",
        ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"),
        ("java",),
        ["vscjava.vscode-gradle"],
        {"*.gradle": "gradle"},
        "Gradle distribution and build tasks",
    )
    MAVEN = (
        "maven",
        ("pom.xml",),
        ("java",),
        NO_EXTENSIONS,
        NO_ASSOCIATIONS,
        "Maven distribution and lifecycle tasks",
    )
    PYTHON = (
        "python",
        ("pyproject.toml", "setup.py", "requirements.txt", "Pipfile", "uv.lock"),
        NO_IMPLIED,
        ["ms-python.python", "ms-python.debugpy"],
        NO_ASSOCIATIONS,
        "Python debugging launch configurations",
    )
    NODE = (
        "node",
        ("package.json", "tsconfig.json", "deno.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"),
        NO_IMPLIED,
        ["dbaeumer.vscode-eslint", "esbenp.prettier-vscode"],
        NO_ASSOCIATIONS,
        "Node/TypeScript tooling",
    )
    # Opt-in only: this one configures the tooling used to develop `mega-snake` itself, so it must
    # never land in a user's repository. It has no key in `--stack` and is excluded from `all`;
    # dropping the marker file in a repository root is the only way to switch it on.
    SNAKE = (
        "snake",
        (SNAKE_MARKER,),
        ("python",),
        NO_EXTENSIONS,
        NO_ASSOCIATIONS,
        "mega-snake's own development launch configurations",
        True,
    )

    def __init__(
        self,
        key: str,
        markers: tuple[str, ...],
        implied_keys: tuple[str, ...],
        extensions: list[str],
        file_associations: dict[str, str],
        description: str,
        opt_in: bool = False,
    ) -> None:
        """Initialize a ProjectStack member with its markers and the artifacts it contributes.

        Parameters:
            key: The lowercase name used by the `--stack` option.
            markers: File names whose presence in the repository root activates the stack.
            implied_keys: Keys of the stacks activated together with this one.
            extensions: Recommended VS Code extensions contributed by the stack.
            file_associations: `files.associations` entries contributed by the stack.
            description: Short explanation shown when the stack list is reported to the user.
            opt_in: Whether the stack is reachable only through its marker file.

        Returns:
            None
        """
        self.key = key
        self.markers = markers
        self.implied_keys = implied_keys
        # Copied, never aliased: several members share the same `NO_EXTENSIONS`/`NO_ASSOCIATIONS`
        # object, so storing the argument itself would let one member's mutation rewrite the others.
        self.extensions = list(extensions)
        self.file_associations = dict(file_associations)
        self.description = description
        self.opt_in = opt_in

    def __str__(self) -> str:
        """Return the user-facing name of the stack.

        Returns:
            str: The stack key.
        """
        return self.key

    @property
    def implied(self) -> tuple["ProjectStack", ...]:
        """Resolve the stacks this one drags along.

        The members are referenced by key instead of by object because an enum member cannot
        reference a sibling while the class body is still being evaluated.

        Returns:
            tuple[ProjectStack, ...]: The implied stacks, empty when the stack stands alone.
        """
        return tuple(from_key(key) for key in self.implied_keys)

    def is_present(self, root: str) -> bool:
        """Check whether the stack's marker files exist in the given directory.

        Parameters:
            root: The directory to inspect, normally the repository root.

        Returns:
            bool: True when at least one marker file exists, False otherwise.
        """
        return any(os.path.exists(os.path.join(root, marker)) for marker in self.markers)


class StackAware(Protocol):
    """Protocol for the workspace artifacts that belong to a single stack."""

    stack: ProjectStack


T = TypeVar("T", bound=StackAware)
V = TypeVar("V")


def selectable_keys() -> list[str]:
    """List the stack keys a user may pass to the `--stack` option.

    `COMMON` is excluded because it is always active, opt-in stacks because they are reachable only
    through their marker file, and `all` is offered as a shortcut to force every stack at once.

    Returns:
        list[str]: The accepted option values, in stack declaration order.
    """
    return [stack.key for stack in ProjectStack if stack is not ProjectStack.COMMON and not stack.opt_in] + [ALL_STACKS]


def from_key(key: str) -> ProjectStack:
    """Resolve a stack from its key.

    Parameters:
        key: The stack key, case-insensitive.

    Raises:
        ValueError: If no stack matches the given key.

    Returns:
        ProjectStack: The matching stack.
    """
    for stack in ProjectStack:
        if stack.key == key.lower():
            return stack
    raise ValueError(f"Unknown project stack: {key}")


@lru_cache(maxsize=None)
def _declaration_order(selected: frozenset[ProjectStack]) -> tuple[ProjectStack, ...]:
    """Rescan the enum once per distinct stack set and remember the order it yields.

    `sort_stacks` runs at least four times on the same active stacks in a single `working-env`
    invocation -- once from `describe_stacks`, once from the `collect_by_stack` behind
    `_get_recommended_extensions`, and twice from the `merge_by_stack` behind `_update_input_props`
    and `_update_file_associations` -- and each run used to rebuild a set and walk the whole
    `ProjectStack` enum to reach the same answer. The answer depends on nothing but the given stacks
    and the declaration order of the enum, and neither of those moves while the process runs.

    The key is a `frozenset` because that is what makes the memo agree with the contract: the order
    a caller happens to hold its stacks in is deliberately irrelevant to the result, so two callers
    holding the same stacks differently have to land on the same entry. The cache is bounded by the
    number of distinct stack sets a process asks about, which is one for a real run.

    Anything that could change a member's position in the enum would have to invalidate this, and
    nothing can: `ProjectStack` is closed at import time.

    Parameters:
        selected: The stacks to order.

    Returns:
        tuple[ProjectStack, ...]: The stacks in declaration order.
    """
    return tuple(stack for stack in ProjectStack if stack in selected)


def sort_stacks(stacks: Iterable[ProjectStack]) -> list[ProjectStack]:
    """Order a stack collection deterministically.

    Stacks travel around as sets, and iterating a set is not stable across runs; every consumer that
    turns them into output goes through this helper instead.

    A fresh list is handed back on every call, never the tuple `_declaration_order` memoizes: the
    callers own what they receive, and sharing the cached object would let one of them reorder the
    answer every later caller gets.

    Parameters:
        stacks: The stacks to order.

    Returns:
        list[ProjectStack]: The stacks in declaration order.
    """
    return list(_declaration_order(frozenset(stacks)))


def _expand_into(stack: ProjectStack, resolved: set[ProjectStack]) -> None:
    """Add a stack and everything it drags along to a set that may already hold part of the answer.

    This is what stops a shared implication from being walked once per stack that names it: with
    both `gradle` and `maven` active, the second one finds `java` already in `resolved` and stops
    there instead of expanding the same subgraph again. Taking the accumulator as an argument is
    what makes the skip possible at all -- `expand` on its own cannot know what its caller already
    has, so it had no choice but to redo the walk and hand back a result the caller then merged.

    The set is updated in place. The pop-time guard is what keeps the walk cycle-safe; the filtered
    `extend` is an optimisation on top of it, keeping already-resolved stacks out of `pending`
    rather than out of `resolved`.

    Parameters:
        stack: The stack to expand.
        resolved: The accumulator, updated in place with the stack and its implications.

    Returns:
        None
    """
    pending: list[ProjectStack] = [stack]
    while pending:
        current: ProjectStack = pending.pop()
        if current in resolved:
            continue
        resolved.add(current)
        pending.extend(implied for implied in current.implied if implied not in resolved)


def expand(stack: ProjectStack) -> set[ProjectStack]:
    """Resolve a stack together with everything it drags along, at any depth.

    The expansion is transitive on purpose: today no stack implies another that implies a third, so
    a single `update(stack.implied)` would be enough — but the depth would then be an assumption
    baked into every call site, and a new stack implying `gradle` would silently arrive without
    `java`. Doing it once here keeps the depth a property of this function alone.

    Parameters:
        stack: The stack to expand.

    Returns:
        set[ProjectStack]: The stack itself plus every stack reachable through its implications.
    """
    resolved: set[ProjectStack] = set()
    _expand_into(stack, resolved)
    return resolved


def detect_stacks(root: Optional[str] = None) -> set[ProjectStack]:
    """Detect the stacks present in a repository from its marker files.

    Only the given directory is inspected — a nested module is not detected on purpose, since a
    recursive scan would happily pick up a `package.json` from a vendored dependency. The `--stack`
    option is the escape hatch for those layouts.

    Parameters:
        root: The directory to inspect. Defaults to the current working directory.

    Returns:
        set[ProjectStack]: The active stacks, always including `COMMON`.
    """
    root = root if root else os.getcwd()
    active: set[ProjectStack] = {ProjectStack.COMMON}
    for stack in ProjectStack:
        if stack.is_present(root):
            _expand_into(stack, active)
    return active


def resolve_stacks(selected: Iterable[str] = (), root: Optional[str] = None) -> set[ProjectStack]:
    """Resolve the stacks to configure, from an explicit selection or by detection.

    Parameters:
        selected: Stack keys requested by the user; `all` forces every stack. When empty, the
            stacks are detected from the repository content.
        root: The directory to inspect when detecting. Defaults to the current working directory.

    Raises:
        ValueError: If a requested key does not match any stack, or names an opt-in one.

    Returns:
        set[ProjectStack]: The active stacks, always including `COMMON`.
    """
    # Lowercased up front so `all` follows the same case-insensitive contract as `from_key`: the
    # CLI never sends anything else through `click.Choice(case_sensitive=False)`, but a direct
    # caller passing `ALL` used to get `ValueError: Unknown project stack: ALL`.
    keys: list[str] = [key.lower() for key in selected]
    if not keys:
        return detect_stacks(root)
    if ALL_STACKS in keys:
        # `all` means every stack a user can ask for, which is not the same as every member: an
        # opt-in stack stays out, or the shortcut would be a way around its marker file.
        return {stack for stack in ProjectStack if not stack.opt_in}
    active: set[ProjectStack] = {ProjectStack.COMMON}
    for key in keys:
        stack: ProjectStack = from_key(key)
        # The marker file is the only way into an opt-in stack, and that rule is stated by this
        # module's own docstring, by the copilot instructions and by `working-env.md`. It used to be
        # enforced one layer above, by `click.Choice(selectable_keys())` -- which does reject
        # `--stack snake` with exit 2, so nothing was reachable through the CLI, but it left the
        # model contradicting the three places that document it. `selectable_keys()` computes the
        # allowed set right here, so the rule belongs here too.
        if stack.opt_in:
            raise ValueError(f"Project stack '{stack.key}' is opt-in and can only be activated by its marker file")
        _expand_into(stack, active)
    return active


def filter_by_stack(members: Iterable[T], stacks: AbstractSet[ProjectStack]) -> list[T]:
    """Keep only the artifacts whose stack is active.

    The stacks are taken as an `AbstractSet` rather than a `set`: the body only ever tests
    membership, and the callers that memoize a filtered result have to key that memo on a
    `frozenset`, which is not a `set` as far as the type checker is concerned.

    Parameters:
        members: The workspace artifacts to filter, normally an enum.
        stacks: The active stacks.

    Returns:
        list[T]: The artifacts belonging to an active stack, in their original order.
    """
    return [member for member in members if member.stack in stacks]


def collect_by_stack(stacks: Iterable[ProjectStack], contribution: Callable[[ProjectStack], Iterable[V]]) -> list[V]:
    """Collect what each active stack contributes to a list, without duplicates.

    Parameters:
        stacks: The active stacks; the order they are given in is irrelevant, `sort_stacks` decides
            the result's order.
        contribution: What the given stack contributes.

    Returns:
        list[V]: Every contributed value, in stack declaration order, first occurrence kept.
    """
    collected: list[V] = []
    for stack in sort_stacks(stacks):
        for value in contribution(stack):
            if value not in collected:
                collected.append(value)
    return collected


def merge_by_stack(
    stacks: Iterable[ProjectStack], contribution: Callable[[ProjectStack], Mapping[str, V]]
) -> dict[str, V]:
    """Merge what each active stack contributes to a mapping.

    The merge is what makes the precedence a property of this function instead of an accident of the
    call site: a key contributed by two stacks takes the value of the one declared last. There is no
    such key today, which is exactly why the rule needs a single home -- the callers used to write
    the entries straight into the workspace as they went, so the *first* stack won there while the
    test helper that mirrored them merged into a dict and let the last one win. Both read as
    obviously correct, and nothing compared them.

    Parameters:
        stacks: The active stacks; the order they are given in is irrelevant, `sort_stacks` decides
            the precedence.
        contribution: What the given stack contributes.

    Returns:
        dict[str, V]: The merged mapping, in stack declaration order.
    """
    merged: dict[str, V] = {}
    for stack in sort_stacks(stacks):
        merged.update(contribution(stack))
    return merged


def describe_stacks(stacks: Iterable[ProjectStack]) -> str:
    """Build a human-readable summary of the active stacks.

    Parameters:
        stacks: The active stacks.

    Returns:
        str: One line per stack, formatted as `key: description`.
    """
    return "\n".join(f"\t{stack.key}: {stack.description}" for stack in sort_stacks(stacks))
