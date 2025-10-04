function l_reload {

    # read prop working_path from properties file
    $ws_config_home = $PSScriptRoot
    $properties_file = "$ws_config_home/src/config.properties"
    $local_config = $(Get-Content $properties_file | Select-String -Pattern "local_config_file_name" | ForEach-Object { $_ -replace "local_config_file_name=", "" })
    $working_path = $(Get-Content $properties_file | Select-String -Pattern "working_path" | ForEach-Object { $_ -replace "working_path=", "" })
    $local_config_file = "$PWD/$working_path/$local_config.ps1"
    if (Test-Path $local_config_file) {
        snake msg -t i "Reloading $local_config_file"
        . $local_config_file
    }
    else {
        snake msg -t w  "No local config file found"
    }
}
function snake {
    $ws_config_home = $PSScriptRoot
    $ws_shell = "powershell"
    $properties_file = "$ws_config_home/src/config.properties"
    if ($IsWindows) {
        $python_virtual_key = "python_virtual_ps1_win"
    } elseif ($IsLinux) {
        $python_virtual_key = "python_virtual_ps1_linux"
    } else {
        $python_virtual_key = "python_virtual_ps1_osx"
    }

    # read prop working_path from properties file
    $re_py_env = $(Get-Content $properties_file | Select-String -Pattern "$python_virtual_key" | ForEach-Object { $_ -replace "$python_virtual_key=", "" })
    $py_module = $(Get-Content $properties_file | Select-String -Pattern "python_module" | ForEach-Object { $_ -replace "python_module=", "" })
    $python_env = "$ws_config_home/$re_py_env"
    & $python_env
    $env:PYTHONPATH = "$ws_config_home"
    
    if ($IsWindows) {
        New-Alias -Scope Local -Name python3 -Value python
    }

    if ($args.Count -eq 0) {
        python3 -m $py_module --shell "$ws_shell" --help
    } else {
        python3 -m $py_module --shell "$ws_shell" $args
    }

    # catch exit code
    $exit_code = $LASTEXITCODE

    deactivate

    $global:LASTEXITCODE = $exit_code

    if ($exit_code -eq 21) {
        . l_reload
    }
}
snake msg -t t -p "snake" ": use this function to set the environment configuration"
. l_reload
snake msg -t t -p "l_reload" ": source this function to reload the local config file"