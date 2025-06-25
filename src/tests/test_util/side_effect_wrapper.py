"""Emulates a function that returns a sequence of values and then a fallback value."""


from typing import Any, Callable

class SideEffectWrapper:
    """Emulates a function that returns a sequence of values and then a fallback value."""
    def __init__(self, fallback_callable):
        self.values = []
        self.fallback = fallback_callable
        self.counter = 0

    def __call__(self, *args, **kwargs)-> Any:
        """Handles the logic of returning values in order and fallback."""
        if self.counter < len(self.values):
            result = self.values[self.counter]
            self.counter += 1
            return result
        return self.fallback(*args, **kwargs)

    def set_values(self, values)-> None:
        """Allows to assign a list of values and reset the counter."""
        self.values = values
        self.counter = 0

    def reset(self, reset_mock: Callable, *args, **kwargs) -> Callable:
        """Resets the counter to 0."""
        self.counter = 0
        reset_mock(*args, **kwargs)

