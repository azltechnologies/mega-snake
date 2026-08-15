The ecosystem is detected from the project's lockfiles, first match wins:

| Marker file | Ecosystem | Auditor |
|---|---|---|
| `uv.lock` | Python/uv | [`pip-audit`](https://github.com/pypa/pip-audit) |
| `build.gradle`, `build.gradle.kts`, `pom.xml` | Java (Gradle/Maven) | [OSV-Scanner](https://github.com/google/osv-scanner) |
| `package-lock.json` | Node | OSV-Scanner |
| *(nothing matches)* | generic fallback | OSV-Scanner |

OSV-Scanner covers the non-Python ecosystems because it reads the same OSV advisory database as
`pip-audit`, so findings stay comparable across stacks instead of depending on one tool per
ecosystem.

Any repo can reuse this by consuming `mgsnake`, regardless of its stack.

## Notes

Issue de-duplication is by exact title and considers closed issues too, so a vulnerability you
already triaged and closed is not filed again on the next run.
