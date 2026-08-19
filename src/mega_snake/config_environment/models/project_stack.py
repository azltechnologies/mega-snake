"""This module contains the model describing the technology stacks a workspace can be configured for.

The workspace configuration used to be Java-centric: `working-env` always offered a Java version and
always wrote the Java/Gradle tasks, launch configurations and extensions, even on a repository that
holds no JVM code at all. `ProjectStack` turns that into data: every stack knows the marker files
that reveal its presence in the repository, plus the VS Code artifacts that only make sense when the
stack is part of the workspace. Everything the workspace generator emits is tagged with the stack it
belongs to, so a stack that is not active simply contributes nothing.
"""

from enum import Enum
import os
from typing import Iterable, Optional, Protocol, TypeVar

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


def sort_stacks(stacks: Iterable[ProjectStack]) -> list[ProjectStack]:
    """Order a stack collection deterministically.

    Stacks travel around as sets, and iterating a set is not stable across runs; every consumer that
    turns them into output goes through this helper instead.

    Parameters:
        stacks: The stacks to order.

    Returns:
        list[ProjectStack]: The stacks in declaration order.
    """
    selected = set(stacks)
    return [stack for stack in ProjectStack if stack in selected]


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
    pending: list[ProjectStack] = [stack]
    while pending:
        current: ProjectStack = pending.pop()
        resolved.add(current)
        pending.extend(implied for implied in current.implied if implied not in resolved)
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
            active.update(expand(stack))
    return active


def resolve_stacks(selected: Iterable[str] = (), root: Optional[str] = None) -> set[ProjectStack]:
    """Resolve the stacks to configure, from an explicit selection or by detection.

    Parameters:
        selected: Stack keys requested by the user; `all` forces every stack. When empty, the
            stacks are detected from the repository content.
        root: The directory to inspect when detecting. Defaults to the current working directory.

    Raises:
        ValueError: If a requested key does not match any stack.

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
        active.update(expand(from_key(key)))
    return active


def filter_by_stack(members: Iterable[T], stacks: set[ProjectStack]) -> list[T]:
    """Keep only the artifacts whose stack is active.

    Parameters:
        members: The workspace artifacts to filter, normally an enum.
        stacks: The active stacks.

    Returns:
        list[T]: The artifacts belonging to an active stack, in their original order.
    """
    return [member for member in members if member.stack in stacks]


def describe_stacks(stacks: Iterable[ProjectStack]) -> str:
    """Build a human-readable summary of the active stacks.

    Parameters:
        stacks: The active stacks.

    Returns:
        str: One line per stack, formatted as `key: description`.
    """
    return "\n".join(f"\t{stack.key}: {stack.description}" for stack in sort_stacks(stacks))
