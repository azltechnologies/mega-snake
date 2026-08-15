Frontend tooling (Apollo and most IDE plugins) cannot work from the raw SDL alone — it needs a full
introspection result to provide autocompletion and type checking. That is why this command emits two
files rather than one: the consolidated `.graphql` schema, and the `.json` introspection payload
those tools consume.

## Output

Writes `schema.graphql` (consolidated SDL) and `schema.json` (introspection) to the
`workspace_temp` folder and opens both in VS Code.

## Notes

Every file under the given directory — subdirectories included — is merged, so the directory is
the unit of composition, not an entry-point file. Keep only schema files in it.
