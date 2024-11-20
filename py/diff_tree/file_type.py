"""Class Module representing a file type in the repository changes."""

import dataclasses
from enum import Enum
from py.util.formatting import ws_error


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
    description: int
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
        Increment the number of files added and add the file to the list of files.

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
        ws_error(f"No FileType with symbol '{id_type}' found.", ValueError(f"No FileType found."))
        return None
