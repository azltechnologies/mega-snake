""" Creates a GraphQL schema file from a given schema path. """

import json
import os
import click
from graphql import build_schema, GraphQLSchema, print_schema, introspection_from_schema
from py.util.formatting import ws_success
from py.util.props import AppProperties
from py.util.util import run_operation


@click.command(
    name="createGraphqlSchema",
    short_help="Creates a GraphQL schema file in the working directory.",
    help="Creates a GraphQL schema file in the working directory.",
    epilog="usage: set_env createGraphqlSchema <schema_path>",
)
@click.argument("schema_path", type=click.STRING)
def create_graphql_schema(schema_path: str) -> None:
    """
    Creates a GraphQL schema file in the working directory.
    """
    props_inst: AppProperties = AppProperties.get_instance()
    schema_abs: str = os.path.abspath(schema_path)
    # verify that the schema path exists and is a directory
    if not os.path.isdir(schema_abs):
        raise NotADirectoryError(f"Schema path is not a directory: {schema_abs}")
    # verify that the schema path is not empty
    if not os.listdir(schema_abs):
        raise FileNotFoundError(f"Schema path is empty: {schema_abs}")
    output_file: str = props_inst.retrieve_property("graphql_schema_file")
    # if the schema file already exists, delete it
    if os.path.exists(output_file):
        os.remove(output_file)

    create_schema(schema_abs, output_file)

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

    introspection_dict = introspection_from_schema(schema)

    # Serialize schema to JSON
    schema_str: str = print_schema(schema)

    output_json = f"{output_file}.json"
    output_graphql = f"{output_file}.graphql"

    # Write to schema.json
    with open(output_json, "w", encoding="utf-8") as json_file:
        json.dump(introspection_dict, json_file, indent=2)

    with open(output_graphql, "w", encoding="utf-8") as json_file:
        json_file.write(schema_str)

    run_operation(f"code {output_graphql}", "Opening GraphQL schema")
    run_operation(f"code {output_json}", "Opening GraphQL schema JSON")

    ws_success(f"GraphQL schema file has been generated in {output_graphql}.")
    ws_success(f"GraphQL schema JSON file has been generated in {output_json}.")
