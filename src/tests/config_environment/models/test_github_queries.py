"""Test for github_queries.py"""

from typing import Generator
from unittest.mock import patch, MagicMock
import pytest
from mega_snake.config_environment.models.github_queries import (
    BaseQueries,
    PrQueries,
    IssuesQueries,
    GH_PR_QUERY,
    GH_ISSUES_QUERY,
)

GH_TEST_SETTING = "githubTests.queries"
GH_TEST_QUERY = f'.settings.["{GH_TEST_SETTING}"]'


@pytest.fixture(name="base_query_add_query_record")
def fixture_base_query_add_query_record() -> Generator[MagicMock]:
    """Mock BaseQueries"""
    with patch("mega_snake.config_environment.models.github_queries.BaseQueries.add_query_record") as mock:
        mock.return_value = {"result": "great"}
        yield mock


def test_to_dict() -> None:
    """Test to_dict"""
    label = "my label"
    query = "my query"
    ins = BaseQueries(label, query)
    result = ins.to_dict()
    assert result["label"] == label
    assert result["query"] == query
    assert len(result) == 2


def test_add_query_record() -> None:
    """Test add_tasks_task"""
    label = "my label"
    query = "my query"

    def _get_data_copy() -> dict[str, str]:
        return {"settings": {GH_TEST_SETTING: [{"label": "task1"}, {"label": "task2"}]}}

    # Test when the query is found
    inst = BaseQueries(label, query)
    jd = _get_data_copy()
    jd["settings"][GH_TEST_SETTING].append({"label": inst.label})
    tasks_found: list[dict[str, str]] = [d for d in jd["settings"][GH_TEST_SETTING] if d["label"] == inst.label]
    assert len(tasks_found) == 1
    result = inst.add_query_record(jd, GH_TEST_QUERY)
    assert result is None

    # Test when the query is not found
    inst = BaseQueries(label, query)
    jd = _get_data_copy()
    tasks_found: list[dict[str, str]] = [d for d in jd["settings"][GH_TEST_SETTING] if d["label"] == inst.label]
    assert not tasks_found
    result = inst.add_query_record(jd, GH_TEST_QUERY)
    tasks_found = [d for d in result["settings"][GH_TEST_SETTING] if d["label"] == inst.label]
    assert tasks_found
    assert len(tasks_found) == 1
    assert tasks_found[0]["label"] == label
    assert tasks_found[0]["query"] == query

    # Test when the query is found but has multiple entries
    inst = BaseQueries(label, query)
    jd = _get_data_copy()
    jd["settings"][GH_TEST_SETTING].append({"label": inst.label})
    jd["settings"][GH_TEST_SETTING].append({"label": inst.label})
    tasks_found: list[dict[str, str]] = [d for d in jd["settings"][GH_TEST_SETTING] if d["label"] == inst.label]
    assert len(tasks_found) == 2
    result = inst.add_query_record(jd, GH_TEST_QUERY)
    tasks_found = [d for d in result["settings"][GH_TEST_SETTING] if d["label"] == inst.label]
    assert tasks_found
    assert len(tasks_found) == 1
    assert tasks_found[0]["label"] == label
    assert tasks_found[0]["query"] == query


def test_add_query_pr_query(base_query_add_query_record: MagicMock) -> None:
    """Test add_query_record for PrQueries"""
    data = {"settings": {GH_TEST_SETTING: [{"label": "task1"}, {"label": "task2"}]}}
    for member in PrQueries:
        member.add_query(data)
        base_query_add_query_record.assert_called_once_with(data, GH_PR_QUERY)
        base_query_add_query_record.reset_mock()


def test_add_query_record_issues_query(base_query_add_query_record: MagicMock) -> None:
    """Test add_query_record for IssuesQueries"""
    data = {"settings": {GH_TEST_SETTING: [{"label": "task1"}, {"label": "task2"}]}}
    for member in IssuesQueries:
        member.add_query(data)
        base_query_add_query_record.assert_called_once_with(data, GH_ISSUES_QUERY)
        base_query_add_query_record.reset_mock()


def test_to_dict_issues_query() -> None:
    """Test to_dict for IssuesQueries"""
    for member in IssuesQueries:
        result = member.to_dict()
        assert result["label"] == member.label
        assert result["query"] == member.query
        arg_count = 2
        if member.group_by:
            assert result["groupBy"] == member.group_by
            arg_count += 1
        assert len(result) == arg_count
