Adds the task definitions under the `tasks` section of the current `.code-workspace` file —
`clean install`, `test`, `verify`, `dependency:tree` and `spring-boot:run` — together with the
matching log watchers, so each task's output lands in a watched log file.

## Notes

Requires a `pom.xml` in the current directory. Existing tasks and watchers are left alone unless
`--override` is passed.
