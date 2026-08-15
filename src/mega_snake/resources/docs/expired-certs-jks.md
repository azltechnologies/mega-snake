Checks a Java KeyStore (JKS) for expired certificates.

Lists aliases and valid dates, creating warnings for expired certs. Uses `keytool` and attempts to parse the date format which depends on the system locale and standard Java output formats.
