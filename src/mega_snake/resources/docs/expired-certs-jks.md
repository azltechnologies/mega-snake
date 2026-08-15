Lists every alias in the keystore with its validity dates and raises a warning for the expired ones,
so you find out before a local dev environment breaks on an expired SSL certificate.

## Examples

```bash
mgsnake expired-certs-jks /path/to/keystore.jks
mgsnake expired-certs-jks /path/to/keystore.jks --password mypassword
```

## Notes

Parsing relies on `keytool -v -list` and expects its standard English date format
(`Mon Jan 01 00:00:00 UTC 2026`), which depends on the system locale and the installed Java
version. An alias without date information is warned about and skipped; a date in an unexpected
format aborts the run with an error rather than reporting a wrong status. For expired
certificates the command prints the `keytool` commands to delete and re-import them.
