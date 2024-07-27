#!/usr/bin/env python3
import re
import sys

text = sys.stdin.read()
my_list = []
pattern = r"\b\d+\b\.?\d*"
matches = re.findall(pattern, text, re.MULTILINE)
matches.sort(reverse=True)
for match in matches:
    print(match)