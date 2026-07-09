# SPDX-License-Identifier: GPL-2.0-only

import enum
from collections.abc import Iterable
from pathlib import Path
from typing import Final, override

from PyQt6 import QtCore

from .elog import Elog
from .model import (
    IMPORTANT,
    READ,
    UNIMPORTANT,
    UNREAD,
    Column,
    ElogModelItem,
    ImportantState,
    ReadState,
    StateStore,
)

Qt = QtCore.Qt
_MODEL_INDEX: Final = QtCore.QModelIndex()


def sourceIndex(index: QtCore.QModelIndex) -> QtCore.QModelIndex:
    model = index.model()
    if not model:
        return index
    return model.mapToSource(index)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownVariableType]


class Role(enum.IntEnum):
    SortRole = Qt.ItemDataRole.UserRole + 1


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
            IMPORTANT if state is Qt.CheckState.Checked else UNIMPORTANT
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
            READ if state is Qt.CheckState.Checked else UNREAD
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

    @override
    def rowCount(self, parent: QtCore.QModelIndex = _MODEL_INDEX) -> int:
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

    @override
    def columnCount(self, parent: QtCore.QModelIndex = _MODEL_INDEX) -> int:
        return len(Column)

    @override
    def removeRows(
        self,
        row: int,
        count: int,
        parent: QtCore.QModelIndex = _MODEL_INDEX,
    ) -> bool:
        last = min(self.rowCount(), row + count)
        self.beginRemoveRows(parent, row, max(row, last - 1))
        idx = -1
        for idx in range(row, row + count):
            del self._data[row]
        self.endRemoveRows()
        return idx > -1

    @override
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
        col = Column(section)
        return {
            Column.ImportantState: "‼",
            Column.ReadState: "Read",
            Column.Eclass: "Type",
        }.get(col, col.name)

    @override
    def flags(self, index: QtCore.QModelIndex) -> Qt.ItemFlag:
        if index.column() in (Column.ImportantState, Column.ReadState):
            return super().flags(index) | Qt.ItemFlag.ItemIsUserCheckable
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

    @override
    def data(
        self,
        index: QtCore.QModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        item = self._data[index.row()]
        col = Column(index.column())
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return {
                Column.Category: item.category(),
                Column.Package: item.package(),
                Column.Eclass: item.eclass().name,
                Column.Date: item.localeTime(),
            }.get(col, "")
        if role == Qt.ItemDataRole.CheckStateRole:
            return {
                Column.ImportantState: item.importantState(),
                Column.ReadState: item.readState(),
            }.get(col)
        if role == Role.SortRole:
            key = {
                Column.ImportantState: item.importantState,
                Column.ReadState: item.readState,
                Column.Date: item.isoTime,
                Column.Eclass: lambda: item.eclass().value,
                Column.Category: item.category().lower,
                Column.Package: item.package().lower,
            }.get(col, lambda: self.data(index, Qt.ItemDataRole.DisplayRole))()
            return f"{key}{item.isoTime()}"
        return None

    @override
    def setData(
        self,
        index: QtCore.QModelIndex,
        value: object,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        try:
            col = Column(index.column())
            {
                Column.ImportantState: self.toggleImportantState,
                Column.ReadState: self.toggleReadState,
            }[col](index)
        except (KeyError, ValueError):
            return super().setData(index, value, role)
        else:
            return True
