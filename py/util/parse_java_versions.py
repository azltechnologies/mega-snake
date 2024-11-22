#!/usr/bin/env python3
import re
import sys

def verify_match(pattern: str, match: str) -> str:
    r = re.search(ver_pattern, match)
    if r:
        return r.group()
    else:
        return ""

text = sys.stdin.read()
pattern = r"^.+\s\-\s\"[\w\s\.]+\"\s/.+$"
matches = re.findall(pattern, text, re.MULTILINE)
result = ""
for m in matches:
    match: str = str(m)
    ver_pattern = r"(?<=\s)/.+$"
    version = verify_match(ver_pattern, match)
    key_pattern = r"^\s+[0-9\._]+"
    key = verify_match(key_pattern, match)
    key_pattern = r"[0-9\._]+"
    key = verify_match(key_pattern, match)
    print(key + ":" + version.replace('"', ""))

