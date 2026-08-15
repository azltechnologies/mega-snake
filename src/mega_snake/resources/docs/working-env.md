The "zero-config start" command: a single run should leave the IDE ready to code, so it is the one
to reach for on a freshly cloned repository.

On top of what the synopsis lists, it also sets up log watchers and GitHub query definitions, and it
 runs the version configuration of every stack it finds — `set-java`, `set-gradle` and `set-maven`
 are only needed afterwards when you want to switch versions.

## Examples

```bash
# Configure whatever the repository looks like (the usual case)
mgsnake working-env

# A Java repository whose build file lives in a subfolder
mgsnake working-env --stack maven

# A polyglot repository: several stacks at once
mgsnake working-env -s gradle -s node

# Everything, like the command used to behave before stack detection
mgsnake working-env --stack all
```

## Notes

Everything the command writes belongs to a *stack*, and only the stacks the repository shows a
marker file for are configured. A workspace on a repository with no JVM build file is never asked
for a JDK, and gets none of the Java tasks, launch configurations, log watchers or extensions:

| Stack | Marker files in the current directory | Brings along |
|---|---|---|
| `gradle` | `build.gradle`, `build.gradle.kts`, `settings.gradle`, `settings.gradle.kts` | `java` |
| `maven` | `pom.xml` | `java` |
| `python` | `pyproject.toml`, `setup.py`, `requirements.txt`, `Pipfile`, `uv.lock` | — |
| `node` | `package.json`, `tsconfig.json`, `deno.json`, `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock` | — |
| `java` | *(none — it comes from a build tool, or from `--stack java`)* | — |
| `common` | *(always active)* | — |

Only the current directory is inspected. A repository that keeps its build file in a subfolder — or
one that uses a build tool this command does not know — needs `--stack`, which replaces the
detection entirely. The per-tool commands stay unconditional either way, so `set-java` still works
in a folder where the Java stack was skipped.

Skipping a stack never removes anything: recommended extensions, tasks and launch configurations
already present in the `.code-workspace` file are left untouched, so a workspace configured before
a stack was dropped keeps working. Remove those entries by hand when you want them gone.

Requires a valid Git repository. Developer-specific overrides are loaded before the defaults are
written, so anything you set through `init-local-config` wins over the values this command
generates.

Because it writes the local environment files, a successful run exits with status `29`. The
`mgsnake` shell function installed by the init script (see `shell-path`) reads that status and
re-sources them, so the environment it just configured applies to the current session.
