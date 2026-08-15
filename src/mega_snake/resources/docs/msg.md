Exposes the internal logging mechanism to the shell. It exists so that the packaged shell scripts
(`config_setup.sh` / `config_setup.ps1`) print success, warning and error messages in exactly the
same format as the Python commands, instead of each one inventing its own `echo`.

## Notes

The message is both printed to the console and written to the workspace log file.
