Creates recommended VS Code tasks for Maven projects:

- Adds Maven tasks to the current `.code-workspace` file under the `tasks` section
- Includes tasks for `clean install`, `test`, `verify`, `dependency:tree`, and `spring-boot:run`
- Requires a `pom.xml` in the current directory
