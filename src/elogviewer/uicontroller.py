# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import glob
import itertools
from pathlib import Path
from typing import Final, Protocol

from PyQt6 import QtCore

from .model import Column
from .uimodel import Model, sourceIndex

Qt = QtCore.Qt


class Config(Protocol):
    @property
    def elogpath(self) -> Path: ...


class StateStore:
    def __init__(self, settings: QtCore.QSettings) -> None:
        self.settings: Final = settings

    def loadRead(self) -> frozenset[Path]:
        return frozenset(Path(p) for p in self.settings.value("readFlag"))

    def loadImportant(self) -> frozenset[Path]:
        return frozenset(Path(p) for p in self.settings.value("importantFlag"))

    def saveRead(self, names: frozenset[Path]) -> None:
        self.settings.setValue("readFlag", frozenset(str(p) for p in names))

    def saveImportant(self, names: frozenset[Path]) -> None:
        self.settings.setValue("importantFlag", frozenset(str(p) for p in names))


class ElogviewerController(QtCore.QObject):
    statusTextChanged = QtCore.pyqtSignal(str)
    unreadTextChanged = QtCore.pyqtSignal(str)
    errorOccurred = QtCore.pyqtSignal(str)
    rowSelectRequested = QtCore.pyqtSignal(int)

    def __init__(
        self,
        model: Model,
        proxyModel: QtCore.QSortFilterProxyModel,
        selectionModel: QtCore.QItemSelectionModel,
        config: Config,
    ) -> None:
        super().__init__()
        self._model = model
        self._proxyModel = proxyModel
        self._selectionModel = selectionModel
        self.config = config
        self.settings = QtCore.QSettings("elogviewer", "elogviewer")
        if not self.settings.contains("readFlag"):
            self.settings.setValue("readFlag", set())
        if not self.settings.contains("importantFlag"):
            self.settings.setValue("importantFlag", set())

    def saveSettings(self) -> None:
        self._model.save(StateStore(self.settings))

    def onCurrentRowChanged(
        self,
        current: QtCore.QModelIndex,
        previous: QtCore.QModelIndex,
    ) -> None:
        if previous.row() != -1:
            model = self._model
            index = model.index(
                sourceIndex(current).row(),
                Column.ReadState,
                current.parent(),
            )
            model.setReadState(index, Qt.CheckState.Checked)
        self.updateStatus()
        self.updateUnreadCount()

    def updateStatus(self) -> None:
        text = "%i of %i elogs" % (self.currentRow() + 1, self._model.elogCount())
        self.statusTextChanged.emit(text)

    def updateUnreadCount(self) -> None:
        self.unreadTextChanged.emit("%i unread" % self._model.unreadCount())

    def currentRow(self) -> int:
        return self._selectionModel.currentIndex().row()

    def rowCount(self) -> int:
        return self._proxyModel.rowCount()

    def setSelectedReadState(self, state: Qt.CheckState) -> None:
        rows = self._selectionModel.selectedRows(Column.ReadState)
        if not rows:
            return
        model = self._model
        model.blockSignals(True)
        try:
            for index in rows:
                model.setReadState(sourceIndex(index), state)
        finally:
            model.blockSignals(False)
        model.dataChanged.emit(
            model.index(0, 0),
            model.index(model.rowCount() - 1, model.columnCount() - 1),
        )
        self.updateUnreadCount()

    def toggleSelectedImportantState(self) -> None:
        rows = self._selectionModel.selectedRows(Column.ImportantState)
        if not rows:
            return
        model = self._model
        firstSourceIndex = sourceIndex(rows[0])
        state = (
            Qt.CheckState.Unchecked
            if model.importantState(firstSourceIndex) is Qt.CheckState.Checked
            else Qt.CheckState.Checked
        )
        model.blockSignals(True)
        try:
            for index in rows:
                model.setImportantState(sourceIndex(index), state)
        finally:
            model.blockSignals(False)
        model.dataChanged.emit(
            model.index(0, Column.ImportantState),
            model.index(model.rowCount() - 1, Column.ImportantState),
        )

    def deleteSelected(self) -> None:
        selection = [
            self._proxyModel.mapToSource(idx)
            for idx in self._selectionModel.selectedRows()
        ]
        selection.sort(key=lambda idx: idx.row())
        # Avoid call to onCurrentRowChanged() by clearing
        # selection with reset().
        currentRow = self.currentRow()
        self._selectionModel.reset()

        filename: Path | None = None
        try:
            for index in reversed(selection):
                filename = self._model.itemFromIndex(index).filename()
                if filename.exists():
                    filename.unlink()
                self._model.removeRow(index.row())
        except OSError as exc:
            self.errorOccurred.emit(
                f"Error while trying to delete '{filename}':<br><b>{exc.strerror}</b>",
            )

        self.rowSelectRequested.emit(min(currentRow, self.rowCount() - 1))
        self.updateStatus()

    def populate(self) -> None:
        currentRow = self.currentRow()
        self._selectionModel.reset()
        self._model.populate(
            (
                Path(f)
                for f in itertools.chain(
                    glob.iglob(str(self.config.elogpath / "*:*:*.log*")),
                    glob.iglob(str(self.config.elogpath / "*" / "*:*.log*")),
                )
            ),
            settings=StateStore(self.settings),
        )
        self.rowSelectRequested.emit(min(currentRow, self.rowCount() - 1))
