# SPDX-License-Identifier: GPL-2.0-only

# The TYPE_CHECKING import of the view is annotation-only: there is no cycle
# at runtime (uiview -> uicontroller is the only executed direction).
# pyright: reportImportCycles=false

from __future__ import annotations

import glob
import itertools
import weakref
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol

from PyQt6 import QtCore, QtWidgets

from .model import Column
from .uimodel import Model, sourceIndex

if TYPE_CHECKING:
    from .uiview import Elogviewer

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


class ElogviewerController:
    def __init__(
        self,
        view: Elogviewer,
        model: Model,
        proxyModel: QtCore.QSortFilterProxyModel,
        selectionModel: QtCore.QItemSelectionModel,
        config: Config,
    ) -> None:
        # The view holds the controller; keep the back-reference weak so the
        # pair does not form a strong reference cycle.
        self._viewRef = weakref.ref(view)
        self._model = model
        self._proxyModel = proxyModel
        self._selectionModel = selectionModel
        self.config = config
        self.settings = QtCore.QSettings("elogviewer", "elogviewer")
        if not self.settings.contains("readFlag"):
            self.settings.setValue("readFlag", set())
        if not self.settings.contains("importantFlag"):
            self.settings.setValue("importantFlag", set())

    @property
    def _view(self) -> Elogviewer:
        # Dereference: sip rejects weakref proxies where a QWidget is expected.
        view = self._viewRef()
        assert view is not None
        return view

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
        self._view.statusLabel.setText(text)

    def updateUnreadCount(self) -> None:
        view = self._view
        text = "%i unread" % self._model.unreadCount()
        view.unreadLabel.setText(text)
        view.setWindowTitle("Elogviewer (%s)" % text)

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
            QtWidgets.QMessageBox.critical(
                self._view,
                "Error",
                f"Error while trying to delete '{filename}':<br><b>{exc.strerror}</b>",
            )

        self._view.tableView.selectRow(min(currentRow, self.rowCount() - 1))
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
        self._view.tableView.selectRow(min(currentRow, self.rowCount() - 1))
