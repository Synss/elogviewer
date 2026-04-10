# SPDX-License-Identifier: GPL-2.0-only

import enum
import io
import time
from collections.abc import Iterable
from contextlib import AbstractContextManager, closing
from pathlib import Path
from typing import IO, NewType, Protocol

from PyQt6 import QtCore

from .eclass import EClass
from .elog import Elog

Qt = QtCore.Qt

ReadState = NewType("ReadState", bool)
ImportantState = NewType("ImportantState", bool)


class Column(enum.IntEnum):
    ImportantState = 0
    Category = 1
    Package = 2
    ReadState = 3
    Eclass = 4
    Date = 5


class Role(enum.IntEnum):
    SortRole = Qt.ItemDataRole.UserRole + 1


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


class Model(QtCore.QAbstractTableModel):
    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._data: list[ElogModelItem] = []  # A list of ElogModelItem.

    def importantState(self, index: QtCore.QModelIndex) -> Qt.CheckState:
        return (
            Qt.CheckState.Checked
            if self.itemFromIndex(index).importantState()
            else Qt.CheckState.Unchecked
        )

    def setImportantState(
        self,
        index: QtCore.QModelIndex,
        state: Qt.CheckState,
    ) -> bool:
        if index.column() != Column.ImportantState:
            return False
        self.itemFromIndex(index).setImportantState(
            ImportantState(True)
            if state is Qt.CheckState.Checked
            else ImportantState(False)
        )
        self.dataChanged.emit(index, index)
        return True

    def toggleImportantState(self, index: QtCore.QModelIndex) -> bool:
        return self.setImportantState(
            index,
            (
                Qt.CheckState.Unchecked
                if self.importantState(index) is Qt.CheckState.Checked
                else Qt.CheckState.Checked
            ),
        )

    def readState(self, index: QtCore.QModelIndex) -> Qt.CheckState:
        return (
            Qt.CheckState.Checked
            if self.itemFromIndex(index).readState()
            else Qt.CheckState.Unchecked
        )

    def setReadState(self, index: QtCore.QModelIndex, state: Qt.CheckState) -> bool:
        if index.column() != Column.ReadState:
            return False
        self.itemFromIndex(index).setReadState(
            ReadState(True) if state is Qt.CheckState.Checked else ReadState(False)
        )
        self.dataChanged.emit(
            self.index(index.row(), 0, index.parent()),
            self.index(index.row(), self.columnCount() - 1, index.parent()),
        )
        return True

    def toggleReadState(self, index: QtCore.QModelIndex) -> bool:
        current = self.readState(index)
        return self.setReadState(
            index,
            Qt.CheckState.Unchecked
            if current == Qt.CheckState.Checked
            else Qt.CheckState.Checked,
        )

    def itemFromIndex(self, index: QtCore.QModelIndex) -> ElogModelItem:
        return self._data[index.row()]

    def item(self, row: int, _column: int = 0) -> ElogModelItem:
        return self._data[row]

    def appendItem(self, item: ElogModelItem) -> None:
        self._data.append(item)

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(self._data)

    def elogCount(self) -> int:
        return self.rowCount()

    def readCount(self) -> int:
        count = 0
        for row in range(self.rowCount()):
            if self.item(row).isReadState():
                count += 1
        return count

    def unreadCount(self) -> int:
        return self.elogCount() - self.readCount()

    def importantCount(self) -> int:
        count = 0
        for row in range(self.rowCount()):
            if self.item(row).isImportantState():
                count += 1
        return count

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(Column)

    def removeRows(
        self,
        row: int,
        count: int,
        parent: QtCore.QModelIndex = QtCore.QModelIndex(),
    ) -> bool:
        last = min(self.rowCount(), row + count)
        self.beginRemoveRows(parent, row, max(row, last - 1))
        idx = -1
        for idx in range(row, row + count):
            self._data.pop(row)
        self.endRemoveRows()
        return idx > -1

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if (
            orientation != Qt.Orientation.Horizontal
            or role != Qt.ItemDataRole.DisplayRole
        ):
            return super().headerData(section, orientation, role)
        return {  # type: ignore
            Column.ImportantState: "!!",
            Column.ReadState: "Read",
            Column.Eclass: "Type",
        }.pop(section, Column(section).name)

    def flags(self, index: QtCore.QModelIndex) -> Qt.ItemFlag:
        if index.column() in (Column.ImportantState, Column.ReadState):
            return super().flags(index) | Qt.ItemFlag.ItemIsEditable
        return super().flags(index)

    def save(self, settings: StateStore) -> None:
        settings.saveRead(
            frozenset(item.filename() for item in self._data if item.isReadState())
        )
        settings.saveImportant(
            frozenset(item.filename() for item in self._data if item.isImportantState())
        )

    def populate(self, filenames: Iterable[Path], *, settings: StateStore) -> None:
        self.removeRows(0, self.rowCount())
        self.beginResetModel()
        readNames = settings.loadRead()
        importantNames = settings.loadImportant()
        for filename in filenames:
            item = ElogModelItem(Elog.fromFilename(filename))
            item.setReadState(ReadState(filename in readNames))
            item.setImportantState(ImportantState(filename in importantNames))
            self.appendItem(item)
        self.endResetModel()

    def data(
        self,
        index: QtCore.QModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        item = self._data[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return {  # type: ignore
                Column.Category: item.category(),
                Column.Package: item.package(),
                Column.Eclass: item.eclass().name,
                Column.Date: item.localeTime(),
            }.get(index.column(), "")
        if role == Qt.ItemDataRole.CheckStateRole:
            return {
                Column.ImportantState: item.importantState(),
                Column.ReadState: item.readState(),
            }.get(index.column())  # type: ignore
        if role == Role.SortRole:
            key = {  # type: ignore
                Column.ImportantState: item.importantState,
                Column.ReadState: item.readState,
                Column.Date: item.isoTime,
                Column.Eclass: lambda: item.eclass().value,
                Column.Category: item.category().lower,
                Column.Package: item.package().lower,
            }.get(
                index.column(),
                lambda: self.data(index, Qt.ItemDataRole.DisplayRole),
            )()
            return f"{key}{item.isoTime()}"
        return None

    def setData(
        self,
        index: QtCore.QModelIndex,
        value: object,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        try:
            {  # type: ignore
                Column.ImportantState: self.toggleImportantState,
                Column.ReadState: self.toggleReadState,
            }[index.column()](index)
        except KeyError:
            return super().setData(index, value, role)
        else:
            return True
