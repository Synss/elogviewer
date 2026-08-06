# SPDX-License-Identifier: GPL-2.0-only

import enum
import io
import time
from contextlib import AbstractContextManager, closing
from pathlib import Path
from typing import IO, Final, Protocol, final

from .eclass import EClass
from .elog import Elog


class _ReadState(enum.Enum):
    READ = enum.auto()
    UNREAD = enum.auto()


READ: Final = _ReadState.READ
UNREAD: Final = _ReadState.UNREAD


class _ImportantState(enum.Enum):
    IMPORTANT = enum.auto()
    UNIMPORTANT = enum.auto()


IMPORTANT: Final = _ImportantState.IMPORTANT
UNIMPORTANT: Final = _ImportantState.UNIMPORTANT


class Column(enum.IntEnum):
    ImportantState = 0
    Category = 1
    Package = 2
    ReadState = 3
    Eclass = 4
    Date = 5


@final
class ElogModelItem:
    def __init__(
        self,
        elog: Elog,
        readState: _ReadState = UNREAD,
        importantState: _ImportantState = UNIMPORTANT,
    ) -> None:
        self._elog = elog
        self._readState = readState
        self._importantState = importantState

    def filename(self) -> Path:
        return self._elog.filename

    def category(self) -> str:
        return self._elog.category

    def package(self) -> str:
        return self._elog.package

    def isoTime(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", self._elog.date)

    def localeTime(self) -> str:
        return time.strftime("%x %X", self._elog.date)

    def eclass(self) -> EClass:
        return self._elog.eclass

    def readState(self) -> _ReadState:
        return self._readState

    def setReadState(self, state: _ReadState) -> None:
        self._readState = state

    def isReadState(self) -> bool:
        return self.readState() is READ

    def importantState(self) -> _ImportantState:
        return self._importantState

    def setImportantState(self, state: _ImportantState) -> None:
        self._importantState = state

    def isImportantState(self) -> bool:
        return self.importantState() is IMPORTANT

    def file(self) -> AbstractContextManager[IO[str]]:
        return closing(io.StringIO(self._elog.contents))


class StateStore(Protocol):
    def loadRead(self) -> frozenset[Path]: ...
    def loadImportant(self) -> frozenset[Path]: ...
    def saveRead(self, names: frozenset[Path]) -> None: ...
    def saveImportant(self, names: frozenset[Path]) -> None: ...
