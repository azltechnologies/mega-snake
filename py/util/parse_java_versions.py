#!/usr/bin/env python3
""" temporal script to parse java versions from a log file """

import re
import sys

def verify_match(pattern: str, match: str) -> str:
    """
    Verifies if the pattern matches the match string and returns the match if it does.

    Args:
        pattern: str
        match: str
    """
    r = re.search(pattern, match)
    if r:
        return r.group()
    return ""

text = sys.stdin.read()
PATTERN = r"^.+\s\-\s\"[\w\s\.]+\"\s/.+$"
matches = re.findall(PATTERN, text, re.MULTILINE)
for m in matches:
    mch: str = str(m)
    VER_PATTERN = r"(?<=\s)/.+$"
    version = verify_match(VER_PATTERN, mch)
    KEY_PATTERN = r"^\s+[0-9\._]+"
    key = verify_match(KEY_PATTERN, mch)
    KEY_PATTERN = r"[0-9\._]+"
    key = verify_match(KEY_PATTERN, mch)
    print(key + ":" + version.replace('"', ""))
