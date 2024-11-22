"""Class Module representing a file type in the repository changes."""

import dataclasses
import os
from enum import Enum
from py.util.formatting import WorkspaceError


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
        create_new_file: None
        from_symbol: FileType

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
        Increment the number of files added and add the file to the list of files.

        Args:
            file: str
        """
        self.added += 1
        self.files.append(file)

    def create_new_file(self, location: str) -> None:
        """
        Returns the new file string path.

        Args:
            location: str

        Returns:
            str
        """
        for file in self.files:
            new_file_path: str = f"{location}/{file} - {self.symbol}"
            os.makedirs(os.path.dirname(new_file_path), exist_ok=True)
            # create the new empty file
            with open(new_file_path, "w", encoding="utf-8") as new_file:
                new_file.write("")

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
        e = ValueError("No FileType found.")
        WorkspaceError.ws_error(e, f"No FileType with symbol '{id_type}' found.")
        raise e

    @classmethod
    def get_changes(cls) -> str:
        """
        Returns the changes made to the repository.

        Returns:
            str
        """
        changes: list[str] = []
        count: int = 0
        for file_type in cls:
            if file_type.added > 0:
                count += file_type.added
                changes.append(f"{file_type.symbol}  {file_type.description}: {file_type.added}\n")
        changes.insert(0, f"{count} files changed\n")
        return "".join(changes)
