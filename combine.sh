#!/bin/bash

# Output file name
output_file="combined_output.txt"
#output_file="/Users/carlosmorales/IdeaProjects/stuff/combined_output.txt"

# Clear the output file if it exists
> "$output_file"
return 0
# Function to process each file
process_file() {
  local file="$1"
  local output_file="$2"
  echo "Processing $file"
  echo "output_file: $output_file"
  echo "________________" >> "$output_file"
  echo "<$(basename "$file")>" >> "$output_file"
  cat "$file" >> "$output_file"
  echo "" >> "$output_file"
}

# Export the function to be used by find
export -f process_file

# Find all .sh and .py files in the current directory recursively and process them
#find . -type f \( -name "*.sh" -o -name "*.py" \) -exec bash -c 'process_file "$0" '$output_file'' {} \;
find . -type f \( -name "*.py" \) -exec bash -c 'process_file "$0" '$output_file'' {} \;

echo "All .sh and .py files have been concatenated into $output_file"
