from pydantic import BaseModel


class FileEntry(BaseModel):
    name: str
    path: str
    type: str
    size: int
    permissions: str
    owner: str
    group: str
    modified: str


class ChmodRequest(BaseModel):
    path: str
    mode: str
    recursive: bool = False


class MkdirRequest(BaseModel):
    path: str


class RenameRequest(BaseModel):
    old_path: str
    new_path: str


class DeleteRequest(BaseModel):
    path: str
    recursive: bool = False
