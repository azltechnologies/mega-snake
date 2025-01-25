""" Tests for the gcloud sign module """
from unittest.mock import patch, MagicMock
import pytest
from codename_snake.gcloud.sign import gcloud_login_env, gcloud_logout,  _user_login, _app_login, _project_set

@pytest.fixture
def mock_os_system():
    with patch('os.system') as mock:
        mock.return_value = 0
        yield mock

@pytest.fixture
def mock_run_operation():
    with patch('codename_snake.gcloud.sign.run_operation') as mock:
        mock.return_value = MagicMock(stdout='test-project')
        yield mock

@pytest.fixture
def mock_get_command_return_code():
    with patch('codename_snake.gcloud.sign.get_command_return_code') as mock:
        mock.return_value = 0
        yield mock

def test_gcloud_login_env_valid_type(mock_os_system, mock_run_operation):
    gcloud_login_env(project="test-project", type_login="B")
    mock_os_system.assert_called()

def test_gcloud_login_env_invalid_type():
    with pytest.raises(ValueError):
        gcloud_login_env(project="test-project", type_login="invalid")

def test_gcloud_logout(mock_os_system):
    gcloud_logout()
    assert mock_os_system.call_count == 2

def test_user_login_already_logged_in(mock_get_command_return_code, mock_os_system):
    _user_login()
    mock_os_system.assert_not_called()

def test_user_login_new_login(mock_get_command_return_code, mock_os_system):
    mock_get_command_return_code.return_value = 1
    _user_login()
    mock_os_system.assert_called_once()

def test_app_login_already_logged_in(mock_get_command_return_code, mock_os_system):
    _app_login()
    mock_os_system.assert_not_called()

def test_app_login_new_login(mock_get_command_return_code, mock_os_system):
    mock_get_command_return_code.return_value = 1
    _app_login()
    mock_os_system.assert_called_once()

def test_project_set_same_project(mock_run_operation, mock_os_system):
    _project_set("test-project")
    mock_os_system.assert_not_called()

def test_project_set_different_project(mock_run_operation, mock_os_system):
    mock_run_operation.return_value = MagicMock(stdout='different-project')
    _project_set("test-project")
    mock_os_system.assert_called_once()

def test_project_set_failed(mock_run_operation, mock_os_system):
    mock_os_system.return_value = 1
    with pytest.raises(RuntimeError):
        _project_set("test-project")
