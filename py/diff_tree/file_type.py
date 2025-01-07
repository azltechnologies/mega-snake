"""Class Module representing a file type in the repository changes."""

import dataclasses
from enum import Enum


@dataclasses.dataclass
class FileType(Enum):
    """
    Class representing a file type in the repository changes.

    Properties:
        symbol: str
        added: int
        description: str

    Methods:
        add: None
        from_symbol: FileType
        get_changes: str

    """

    ADDED = ("🅐", "A", "FILES ADDED")
    MODIFED = ("🅜", "M", "FILES MODIFED")
    DELETED = ("🅓", "D", "FILES DELETED")
    RENAMED = ("🅡", "R", "FILES RENAMED")
    COPIED = ("🅒", "C", "FILES COPIED")
    TYPECHANGED = ("🅣", "T", "FILES TYPECHANGED")
    UNMERGED = ("🅤", "U", "FILES UNMERGED")

    symbol: str
    id_type: str
    description: str
    added: int
    files: list[str]

    def __init__(self, symbol: str, id_type: str, description: str) -> None:
        self.symbol = symbol
        self.id_type = id_type
        self.description = description
        self.added = 0
        self.files = []

    def add(self, file: str) -> None:
        """
        Increments the added count and appends the file to the files list.

        Args:
            file: str
        """
        self.added += 1
        self.files.append(file)

    @classmethod
    def from_symbol(cls, id_type: str) -> "FileType":
        """
        Returns the FileType with the given symbol.

        Args:
            symbol: str
        """
        for file_type in cls:
            if file_type.id_type == id_type:
                return file_type
        raise ValueError(f"No FileType with symbol '{id_type}' found.")

    @classmethod
    def get_changes(cls) -> str:
        """
        Returns the changes made to the repository.
        """
        changes: list[str] = []
        count: int = 0
        for file_type in cls:
            if file_type.added > 0:
                count += file_type.added
                changes.append(f"{file_type.symbol}  {file_type.description}: {file_type.added}\n")
        changes.insert(0, f"{count} files changed\n")
        return "".join(changes)
