# Sets MEGA_SNAKE_SHELL for the current PowerShell session.
# Defines `mgsnake_reload` to dot-source the local configuration file (if present).
# Prints basic usage hints for `mgsnake` and `mgsnake_reload`.

$env:MEGA_SNAKE_SHELL = "powershell"

function mgsnake_reload {

    $local_config_file = mgsnake get-local-config-path
    if (Test-Path $local_config_file) {
        mgsnake msg -t i "Reloading $local_config_file"
        . $local_config_file
    }
    else {
        mgsnake msg -t w  "No local config file found"
    }
}

function mgsnake_load_env {
    param(
        [string]$Path = ".env"
    )
    if (!(Test-Path $Path)) { return }

    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        
        # Ignorar líneas vacías y comentarios
        if ($line -and !$line.StartsWith('#') -and $line -match '^([^=]+)=(.*)$') {
            $key = $Matches[1].Trim()
            
            # Remover comillas externas (simples o dobles) si existen
            $value = $Matches[2].Trim() -replace '^["'']|["'']$'
            
            # Asignar a las variables de entorno del proceso actual
            [Environment]::SetEnvironmentVariable($key, $value, 'Process')
        }
    }
    mgsnake msg -t t -p "mgsnake_load_env" ": Environment variables loaded from $env_file"
}

mgsnake msg -t t -p "mgsnake" ": use this function to set the environment configuration"
mgsnake_reload
mgsnake msg -t t -p "mgsnake_reload" ": use this function to reload the local config file"