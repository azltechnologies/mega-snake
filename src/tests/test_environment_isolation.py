"""Proves the autouse isolation fixture in `conftest.py` actually runs before every test.

`JIRA_DOMAIN` is set on the *real* process environment below, at import time -- before any fixture
for any test in the whole session has run. That is the only way to simulate "this variable was
already in the shell when pytest started" (the scenario `_isolated_environment` exists to defend
against): setting it from inside a test body would prove nothing, since the autouse fixture has
already finished clearing the environment by the time a test's body starts running -- anything set
there is deliberate injection, the same as `jira_workspace`'s token, not a leak.

`Store` itself never reads the environment at import time (nothing is read from disk, or from
`os.environ`, until the first `get`), so importing it above the assignment below is safe.
"""

import os
from pathlib import Path

import pytest

from mega_snake.constants import JIRA_DOMAIN_KEY
from mega_snake.util.store import Store

os.environ["JIRA_DOMAIN"] = "leaked-before-any-fixture.example.com"


def test_the_real_environment_cannot_leak_into_the_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A variable already in the process environment before pytest started must not reach the store.

    Without the autouse fixture, `Store.get` would resolve `jira.domain` from this variable -- reads
    check the environment first and it outranks every scope (§4.4) -- and return the leaked value
    instead of `None`.

    The store's *disk* location is isolated here (an empty `tmp_path` as the global config dir, an
    unrelated directory as cwd) precisely so that only the environment variable is left as a possible
    source of the leak this test is about -- a real `~/.config/mgsnake/state.json` on the machine
    running the suite must not also answer for `jira.domain` and mask the assertion for the wrong
    reason.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "home" / "AppData"))
    monkeypatch.chdir(tmp_path)
    Store.reset_instance()

    assert Store.get_instance().get(JIRA_DOMAIN_KEY) is None
    Store.reset_instance()
