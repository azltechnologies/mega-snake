"""Utilities for testing"""

from typing import Callable, Any
import pytest


def param_injector(request: pytest.FixtureRequest, *fixture_names: str, **dec_kwargs) -> Callable:
    """Injects variables and pytest fixtures for the __resources_path_validator private method."""

    def decorator(func: Callable) -> Callable:
        """Decorator function."""

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            """Wrapper function."""
            nonlocal dec_kwargs
            additional_mocks = dec_kwargs.pop("more_mocks", {})
            mocks = dec_kwargs.pop("mocks", kwargs.pop("mocks", {}))
            mocks.update(additional_mocks)
            for key, value in dec_kwargs.items():
                kwargs[key] = value
            if fixture_names and request:
                for name in fixture_names:
                    try:
                        fixture_value = request.getfixturevalue(name)
                        mocks[name] = fixture_value
                    except pytest.FixtureLookupError:
                        print(f"Fixture '{name}' not found.")
            kwargs["mocks"] = mocks
            return func(*args, **kwargs)

        return wrapper

    return decorator
