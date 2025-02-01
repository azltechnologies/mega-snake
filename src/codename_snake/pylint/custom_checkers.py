"""Custom checkers for Pylint."""

# custom_checkers.py
from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseChecker

if TYPE_CHECKING:
    from pylint.lint import PyLinter

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class FunctionPatternChecker(BaseChecker):
    """Checker for specific function definition patterns."""

    name = "MissingReturnTypeChecker"
    priority = -1
    msgs = {
        "W9001": (
            "Module %s | %s function | Missing return type in its definition",
            "missing-return-type",
            "Function definition misses a return type",
        ),
    }

    def __init__(self, linter: "PyLinter") -> None:
        super().__init__(linter)

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Visit function definitions and check against pattern."""
        # Get the function definition line
        if not node.returns and not node.name in {"__init__", "__new__"}:
            module_name: str = node.root().name
            self.add_message("missing-return-type", node=node, args=(module_name, node.name))


def register(linter: "PyLinter") -> None:
    """Register the checker."""
    linter.register_checker(FunctionPatternChecker(linter))
