function set_env {
    $ws_config_home=$PSScriptRoot
    $ws_shell="powershell"
    $properties_file="$ws_config_home/config.properties"

    # read prop working_path from properties file
    $re_py_env=$(Get-Content $properties_file | Select-String -Pattern "python_virtual_ps1" | ForEach-Object { $_ -replace "python_virtual_ps1=", "" })
    $py_module=$(Get-Content $properties_file | Select-String -Pattern "python_module" | ForEach-Object { $_ -replace "python_module=", "" })
    $python_env="$ws_config_home/$re_py_env"
    & $python_env
    $env:PYTHONPATH="$ws_config_home"
    
    python3 -m $py_module --shell "$ws_shell" $args

    # catch exit code
    $exit_code=$LASTEXITCODE

    deactivate

    return $exit_code
}