import os
import re

commands = [
    "working-env",
    "set-java",
    "set-gradle",
    "set-maven",
    "maven-project-setup",
    "init-local-config",
    "graphql-schema",
    "diff-tree",
    "remote-branches-details",
    "remote-branches-cleanup",
    "create-release",
    "expired-certs-jks",
    "msg",
    "shell-path",
    "get-local-config-path",
    "scan-dependencies"
]

os.makedirs("src/mega_snake/resources/docs", exist_ok=True)

for cmd in commands:
    with open(f"src/mega_snake/resources/docs/{cmd}.md", "w") as f:
        f.write("")
