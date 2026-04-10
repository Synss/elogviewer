# SPDX-License-Identifier: GPL-2.0-only

import enum
import io
import time
from contextlib import AbstractContextManager, closing
from pathlib import Path
from typing import IO, NewType, Protocol

from .eclass import EClass
from .elog import Elog

ReadState = NewType("ReadState", bool)
ImportantState = NewType("ImportantState", bool)


class Column(enum.IntEnum):
    ImportantState = 0
    Category = 1
    Package = 2
    ReadState = 3
    Eclass = 4
    Date = 5


class ElogModelItem:
    def __init__(
        self,
        elog: Elog,
        readState: ReadState = ReadState(False),
        importantState: ImportantState = ImportantState(False),
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

    def readState(self) -> ReadState:
        return self._readState

    def setReadState(self, state: ReadState) -> None:
        self._readState = state

    def isReadState(self) -> bool:
        return self.readState() == ReadState(True)

    def toggleReadState(self) -> None:
        self.setReadState(ReadState(False) if self.isReadState() else ReadState(True))

    def importantState(self) -> ImportantState:
        return self._importantState

    def setImportantState(self, state: ImportantState) -> None:
        self._importantState = state

    def isImportantState(self) -> bool:
        return self.importantState() == ImportantState(True)

    def toggleImportantState(self) -> None:
        self.setImportantState(
            ImportantState(False) if self.isImportantState() else ImportantState(True)
        )

    def file(self) -> AbstractContextManager[IO[str]]:
        return closing(io.StringIO(self._elog.contents))


class StateStore(Protocol):
    def loadRead(self) -> frozenset[Path]: ...
    def loadImportant(self) -> frozenset[Path]: ...
    def saveRead(self, names: frozenset[Path]) -> None: ...
    def saveImportant(self, names: frozenset[Path]) -> None: ...
