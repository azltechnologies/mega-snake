import re

with open("README.md", "r") as f:
    content = f.read()

# Replace the Available Commands section with a stub
stub = """### Available Commands

[See COMMANDS.md for the full list of available commands and their usage.](COMMANDS.md)"""

# We need to find "### Available Commands" (line 107) and end before "## Automated dependency vulnerability scanning" (line 254)
import re
new_content = re.sub(
    r'### Available Commands.*?## Automated dependency vulnerability scanning',
    stub + '\n\n## Automated dependency vulnerability scanning',
    content,
    flags=re.DOTALL
)

# Now modify the "Automated dependency vulnerability scanning" section.
# Remove the bullet point for mgsnake scan-dependencies.
new_content = re.sub(
    r'- \*\*`mgsnake scan-dependencies`\*\*: audits the project\'s dependencies with.*?regardless of its stack\.',
    '',
    new_content,
    flags=re.DOTALL
)

with open("README.md", "w") as f:
    f.write(new_content)

