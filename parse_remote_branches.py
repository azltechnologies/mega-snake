#!/usr/bin/env python3
import sys
from typing import List
from remote_branch import RemoteBranch

def define_branches(line: str):
    """
    Converts a string into a remote_branch instance

    Args:
        line: str

    Returns:
        RemoteBranch
    """
    return RemoteBranch(line)

text = sys.stdin.read()
array_of_strings = text.split('\n')
branches: List[RemoteBranch] = map(define_branches, array_of_strings)
for branch in branches:
    print(branch.__repr__)
    