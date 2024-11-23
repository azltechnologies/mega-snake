$env:WS_CONFIG_HOME=$PSScriptRoot

function set_env {
    $properties_file="$env:WS_CONFIG_HOME/config.properties"

    # read prop working_path from properties file
    $env:WS_TEMP=$(Get-Content $properties_file | Select-String -Pattern "working_path" | ForEach-Object { $_ -replace "working_path=", "" })
    $re_py_env=$(Get-Content $properties_file | Select-String -Pattern "python_virtual_ps1" | ForEach-Object { $_ -replace "python_virtual_ps1=", "" })
    $py_module=$(Get-Content $properties_file | Select-String -Pattern "python_module" | ForEach-Object { $_ -replace "python_module=", "" })
    $python_env="$env:WS_CONFIG_HOME/$re_py_env"
    & $python_env
    $env:PYTHONPATH="$env:WS_CONFIG_HOME"
    
    python3 -m $py_module $args
}