""" Creates a GraphQL schema file from a given schema path. """

import os
from graphql import build_schema, GraphQLSchema, print_schema
from py.util.formatting import ws_success
from py.util.util import run_operation


def create_schema(schema_path: str, output_file: str) -> None:
    """
    Creates a GraphQL schema file from a given schema path.

    Args:
        schema_path: str
    """

    # get all files in schema path and subdirectories
    schema_files: list[str] = []
    for root, _, files in os.walk(schema_path):
        for file in files:
            schema_files.append(os.path.join(root, file))

    schema_content = ""
    for file in schema_files:
        with open(file, "r", encoding="utf-8") as file_output:
            schema_content += file_output.read()

    # Build schema
    schema: GraphQLSchema = build_schema(schema_content)

    # Serialize schema to JSON
    schema_str: str = print_schema(schema)

    # Write to schema.json
    with open(output_file, "w", encoding="utf-8") as json_file:
        json_file.write(schema_str)

    run_operation(f"code {output_file}", "Opening GraphQL schema")
    ws_success(f"GraphQL schema file has been generated in {output_file}.")
