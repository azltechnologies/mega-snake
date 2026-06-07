"""Focused coverage tests for props helper branches."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codename_snake.util import props as props_module


def test_get_validated_input_proxy_delegates_to_util_module() -> None:
    """The local proxy should delegate to the util implementation."""
    with patch("codename_snake.util.util.get_validated_input", return_value="bash") as util_input:
        assert props_module.get_validated_input("shell?", ["bash"]) == "bash"

    util_input.assert_called_once_with("shell?", ["bash"])


@pytest.mark.parametrize(
    ("files_side_effect", "match"),
    [
        (ModuleNotFoundError("missing module"), "Cannot access package resources for module 'codename_snake'"),
        ("", "Cannot access package resources for module 'codename_snake'"),
    ],
)
def test_init_app_properties_wraps_package_root_errors(files_side_effect: object, match: str) -> None:
    """init_app_properties should surface package resource lookup failures clearly."""
    with patch("codename_snake.util.props.files") as files_mock:
        if isinstance(files_side_effect, BaseException):
            files_mock.side_effect = files_side_effect
        else:
            files_mock.return_value = files_side_effect

        with pytest.raises(ModuleNotFoundError, match=match):
            props_module.init_app_properties("INFO", "bash", False)


@pytest.mark.parametrize(
    ("requested_shell", "fallback_shell"),
    [("powershell", "pwsh"), ("pwsh", "powershell")],
)
def test_init_app_properties_falls_back_between_powershell_variants(
    requested_shell: str, fallback_shell: str
) -> None:
    """init_app_properties should accept the alternate PowerShell executable when available."""
    properties = {"resources_path": "resources"}
    app_properties = MagicMock()
    app_properties._retrieve_property.return_value = "/tmp/snake.log"  # pylint: disable=protected-access
    app_properties.log_level = 20

    with patch("codename_snake.util.props._get_package_root", return_value="/pkg"), patch(
        "codename_snake.util.props.os.path.exists", return_value=True
    ), patch("codename_snake.util.props._read_properties", return_value=properties), patch(
        "codename_snake.util.props.shutil.which",
        side_effect=lambda shell: (
            None if shell == requested_shell else f"/bin/{shell}" if shell == fallback_shell else None
        ),
    ), patch("codename_snake.util.props.AppProperties", return_value=app_properties) as app_properties_class, patch(
        "codename_snake.util.props.formatting.config_log"
    ), patch("codename_snake.util.props.formatting.ws_advice"):
        app_properties_class.get_instance.return_value = app_properties

        props_module.init_app_properties("INFO", requested_shell, False)

    app_properties_class.assert_called_once_with("INFO", fallback_shell, properties)


def test_init_app_properties_rejects_invalid_shell_values_during_validation(tmp_path: Path) -> None:
    """init_app_properties should still reject shells outside SHELL_OPT during AppProperties validation."""
    (tmp_path / "config.properties").write_text("", encoding="utf-8")
    (tmp_path / "resources").mkdir()
    properties = {
        "resources_path": "resources",
        "working_path": str(tmp_path),
        "log_file_name": "snake",
        "local_config_file_name": ".snake.sh",
        "graphql_schema_file_name": "schema.graphql",
    }

    props_module.AppProperties._instance = None  # pylint: disable=protected-access
    try:
        with patch("codename_snake.util.props._get_package_root", return_value=str(tmp_path)), patch(
            "codename_snake.util.props._read_properties", return_value=properties
        ), patch("codename_snake.util.props.shutil.which", return_value="/bin/fish"), patch(
            "codename_snake.util.props._find_code_workspace_files", return_value="workspace.code-workspace"
        ), patch("codename_snake.util.props.formatting.config_log"), patch(
            "codename_snake.util.props.formatting.ws_advice"
        ):
            with pytest.raises(ValueError, match="Invalid shell: fish"):
                props_module.init_app_properties("INFO", "fish", False)
    finally:
        props_module.AppProperties._instance = None  # pylint: disable=protected-access
