from typing import Final, TypedDict

class Settings(TypedDict):
    EPREFIX: str
    PORT_LOGDIR: str

settings: Final[Settings]
