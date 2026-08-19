"""Test for the ProjectStack model"""

import os
from pathlib import Path
from typing import Any
import pytest
from mega_snake.config_environment.models.project_stack import (
    ALL_STACKS,
    SNAKE_MARKER,
    expand,
    NO_ASSOCIATIONS,
    NO_EXTENSIONS,
    ProjectStack,
    describe_stacks,
    detect_stacks,
    filter_by_stack,
    from_key,
    resolve_stacks,
    selectable_keys,
    sort_stacks,
)


def _write_marker(root: Path, marker: str) -> None:
    """Create an empty marker file inside the given folder"""
    (root / marker).write_text("", encoding="utf-8")


def test_enum_members() -> None:
    """Test that every stack exposes the fields the workspace generator consumes"""
    assert len(ProjectStack) > 0
    for member in ProjectStack:
        assert member.key
        assert member.key == member.key.lower()
        assert member.description
        assert isinstance(member.markers, tuple)
        assert isinstance(member.implied_keys, tuple)
        assert isinstance(member.extensions, list)
        assert isinstance(member.file_associations, dict)
        assert str(member) == member.key
    # the shared stack is not tied to any marker: it is always part of the workspace
    assert not ProjectStack.COMMON.markers
    # the build tools drag their language along
    assert ProjectStack.GRADLE.implied == (ProjectStack.JAVA,)
    assert ProjectStack.MAVEN.implied == (ProjectStack.JAVA,)
    assert ProjectStack.PYTHON.implied == ()


def test_no_stack_shares_its_mutable_fields() -> None:
    """Test that the empty sentinels are copied, so one stack can never rewrite another"""
    # every member holds its own objects: several of them are declared with the same sentinel
    for member in ProjectStack:
        assert member.extensions is not NO_EXTENSIONS
        assert member.file_associations is not NO_ASSOCIATIONS
        for other in ProjectStack:
            if other is member:
                continue
            assert member.extensions is not other.extensions
            assert member.file_associations is not other.file_associations

    # mutating one member leaves the sentinels and the other members untouched
    java_extensions: list[str] = list(ProjectStack.JAVA.extensions)
    node_associations: dict[str, str] = dict(ProjectStack.NODE.file_associations)
    ProjectStack.MAVEN.extensions.append("some.extension")
    ProjectStack.PYTHON.file_associations["*.foo"] = "bar"
    try:
        assert NO_EXTENSIONS == []
        assert NO_ASSOCIATIONS == {}
        assert ProjectStack.JAVA.extensions == java_extensions
        assert ProjectStack.NODE.file_associations == node_associations
    finally:
        ProjectStack.MAVEN.extensions.remove("some.extension")
        del ProjectStack.PYTHON.file_associations["*.foo"]


def test_selectable_keys() -> None:
    """Test the values accepted by the --stack option"""
    keys: list[str] = selectable_keys()
    # 'common' is always active, so it is not offered
    assert ProjectStack.COMMON.key not in keys
    # an opt-in stack is reachable only through its marker file, never through the option
    assert ProjectStack.SNAKE.key not in keys
    assert ALL_STACKS in keys
    for member in ProjectStack:
        if member is not ProjectStack.COMMON and not member.opt_in:
            assert member.key in keys
    # the order is stable, since the option help is generated from it
    assert keys == ["java", "gradle", "maven", "python", "node", ALL_STACKS]


def test_from_key() -> None:
    """Test resolving a stack from its key"""
    for member in ProjectStack:
        assert from_key(member.key) is member
        assert from_key(member.key.upper()) is member
    with pytest.raises(ValueError, match="Unknown project stack: cobol"):
        from_key("cobol")


def test_is_present(tmp_path: Path) -> None:
    """Test the marker detection of a single stack"""
    assert not ProjectStack.MAVEN.is_present(str(tmp_path))
    _write_marker(tmp_path, "pom.xml")
    assert ProjectStack.MAVEN.is_present(str(tmp_path))
    # a stack without markers is never detected on its own
    assert not ProjectStack.JAVA.is_present(str(tmp_path))


def test_sort_stacks() -> None:
    """Test that a stack set is always ordered by declaration"""
    unordered: set[ProjectStack] = {ProjectStack.MAVEN, ProjectStack.COMMON, ProjectStack.JAVA}
    assert sort_stacks(unordered) == [ProjectStack.COMMON, ProjectStack.JAVA, ProjectStack.MAVEN]
    assert sort_stacks([]) == []
    # duplicates are collapsed
    assert sort_stacks([ProjectStack.NODE, ProjectStack.NODE]) == [ProjectStack.NODE]


def test_detect_stacks(tmp_path: Path) -> None:
    """Test the detection of the stacks from the repository content"""
    # an empty folder only gets the shared stack
    assert detect_stacks(str(tmp_path)) == {ProjectStack.COMMON}

    # a gradle build file brings java along
    _write_marker(tmp_path, "build.gradle.kts")
    assert detect_stacks(str(tmp_path)) == {ProjectStack.COMMON, ProjectStack.GRADLE, ProjectStack.JAVA}

    # a polyglot repository gets every stack it shows a marker for
    _write_marker(tmp_path, "pyproject.toml")
    _write_marker(tmp_path, "pom.xml")
    assert detect_stacks(str(tmp_path)) == {
        ProjectStack.COMMON,
        ProjectStack.GRADLE,
        ProjectStack.JAVA,
        ProjectStack.MAVEN,
        ProjectStack.PYTHON,
    }

    # a marker in a nested folder is not detected: only the given root is inspected
    nested: Path = tmp_path / "frontend"
    nested.mkdir()
    _write_marker(nested, "package.json")
    assert ProjectStack.NODE not in detect_stacks(str(tmp_path))
    assert ProjectStack.NODE in detect_stacks(str(nested))


def test_detect_stacks_activates_the_opt_in_stack_only_through_its_marker(tmp_path: Path) -> None:
    """Test that the development stack appears exactly when its marker file does."""
    _write_marker(tmp_path, "pyproject.toml")
    assert ProjectStack.SNAKE not in detect_stacks(str(tmp_path))

    _write_marker(tmp_path, SNAKE_MARKER)
    detected: set[ProjectStack] = detect_stacks(str(tmp_path))
    assert ProjectStack.SNAKE in detected
    # it drags Python along, since the launch it contributes is a debugpy one
    assert ProjectStack.PYTHON in detected


def test_expand_resolves_implications_transitively() -> None:
    """Test that expanding a stack returns everything reachable through its implications."""
    assert expand(ProjectStack.NODE) == {ProjectStack.NODE}
    assert expand(ProjectStack.GRADLE) == {ProjectStack.GRADLE, ProjectStack.JAVA}
    assert expand(ProjectStack.MAVEN) == {ProjectStack.MAVEN, ProjectStack.JAVA}
    # the opt-in stack reaches Python, and nothing reaches back into it
    assert expand(ProjectStack.SNAKE) == {ProjectStack.SNAKE, ProjectStack.PYTHON}
    for stack in ProjectStack:
        if stack is not ProjectStack.SNAKE:
            assert ProjectStack.SNAKE not in expand(stack), f"{stack.key} drags the development stack along"


def test_detect_stacks_defaults_to_the_current_directory(tmp_path: Path, monkeypatch: Any) -> None:
    """Test that the detection falls back to the working directory"""
    _write_marker(tmp_path, "package.json")
    monkeypatch.chdir(tmp_path)
    assert detect_stacks() == {ProjectStack.COMMON, ProjectStack.NODE}
    assert os.getcwd() == str(tmp_path)


def test_resolve_stacks(tmp_path: Path) -> None:
    """Test the resolution of the stacks to configure"""
    _write_marker(tmp_path, "pom.xml")

    # without a selection the stacks are detected
    assert resolve_stacks(root=str(tmp_path)) == {ProjectStack.COMMON, ProjectStack.JAVA, ProjectStack.MAVEN}

    # an explicit selection replaces the detection, and still implies the language
    assert resolve_stacks(["gradle"], str(tmp_path)) == {
        ProjectStack.COMMON,
        ProjectStack.GRADLE,
        ProjectStack.JAVA,
    }

    # several stacks can be requested at once
    assert resolve_stacks(["java", "node"], str(tmp_path)) == {
        ProjectStack.COMMON,
        ProjectStack.JAVA,
        ProjectStack.NODE,
    }

    # 'all' forces every stack a user may ask for -- and no opt-in stack, or the shortcut would be a
    # way around the marker file that guards it
    assert resolve_stacks([ALL_STACKS], str(tmp_path)) == {
        stack for stack in ProjectStack if stack is not ProjectStack.SNAKE
    }
    assert ProjectStack.SNAKE not in resolve_stacks([ALL_STACKS], str(tmp_path))

    # 'all' follows the same case-insensitive contract as every other key
    assert resolve_stacks(["ALL"], str(tmp_path)) == resolve_stacks([ALL_STACKS], str(tmp_path))
    assert resolve_stacks(["GRADLE"], str(tmp_path)) == resolve_stacks(["gradle"], str(tmp_path))

    # the opt-in stack is still resolvable by name, for the workspace that drops its marker
    assert ProjectStack.SNAKE in resolve_stacks([ProjectStack.SNAKE.key], str(tmp_path))

    # an unknown key is rejected
    with pytest.raises(ValueError):
        resolve_stacks(["cobol"], str(tmp_path))


def test_filter_by_stack() -> None:
    """Test that only the members of the active stacks survive the filter"""

    class Artifact:  # pylint: disable=R0903
        """Minimal stack-aware artifact"""

        def __init__(self, stack: ProjectStack) -> None:
            """Store the stack the artifact belongs to"""
            self.stack = stack

    common = Artifact(ProjectStack.COMMON)
    java = Artifact(ProjectStack.JAVA)
    node = Artifact(ProjectStack.NODE)
    members: list[Artifact] = [common, java, node]

    assert filter_by_stack(members, {ProjectStack.COMMON}) == [common]
    # the original order is preserved
    assert filter_by_stack(members, {ProjectStack.NODE, ProjectStack.COMMON}) == [common, node]
    assert filter_by_stack(members, set(ProjectStack)) == members
    assert filter_by_stack(members, set()) == []


def test_describe_stacks() -> None:
    """Test the human-readable summary of the active stacks"""
    result: str = describe_stacks({ProjectStack.JAVA, ProjectStack.COMMON})
    lines: list[str] = result.splitlines()
    assert len(lines) == 2
    # the summary is ordered and names both the key and what the stack contributes
    assert lines[0].strip() == f"{ProjectStack.COMMON.key}: {ProjectStack.COMMON.description}"
    assert lines[1].strip() == f"{ProjectStack.JAVA.key}: {ProjectStack.JAVA.description}"
    assert describe_stacks([]) == ""
