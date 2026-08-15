Scans the project's locked dependencies for known vulnerabilities against the [OSV](https://osv.dev) advisory database. Multiple ecosystems are supported: the auditor is auto-detected from the project's lockfiles, or can be forced explicitly.

**Ecosystem detection** (in order, first match wins):
- `uv.lock` present → **Python/uv**, audited with [`pip-audit`](https://github.com/pypa/pip-audit).
- `build.gradle`, `build.gradle.kts` or `pom.xml` present → **Java** (Gradle/Maven).
- `package-lock.json` present → **Node**.
- Nothing matches → generic **osv** fallback.
- Java, Node and the generic fallback are all audited with [OSV-Scanner](https://github.com/google/osv-scanner), which supports many lockfile formats out of the box and reads the same OSV advisory database as `pip-audit`.

For each vulnerability found, opens a GitHub issue (via the `gh` CLI) containing the affected package, installed version, recommended version, severity and a link to the advisory. Skips filing an issue when one with the same title already exists (open or closed), to avoid duplicates. Any repo can reuse this by consuming `mgsnake`, regardless of its stack.
