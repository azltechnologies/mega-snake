#!/usr/bin/env python3
import re
import sys

text = sys.stdin.read()
my_dictionary = {}
pattern = r"^.+\s\-\s\"[\w\s\.]+\"\s/.+$"
matches = re.findall(pattern, text, re.MULTILINE)
result = ''
for match in matches:
    ver_pattern = r"(?<=\s)/.+$"
    version = re.search(ver_pattern,match).group()
    key_pattern = r"^\s+[0-9\._]+"
    key = re.search(key_pattern,match).group()
    key_pattern = r"[0-9\._]+"
    key = re.search(key_pattern,match).group()
    print(key + ':' + version.replace("\"",""))