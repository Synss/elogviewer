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
from .uimodel import sourceIndex

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
    def __init__(self, view: Elogviewer, config: Config) -> None:
        # The view holds the controller; keep the back-reference weak so the
        # pair does not form a strong reference cycle.
        self._viewRef = weakref.ref(view)
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
        view = self._view
        view.model.save(StateStore(self.settings))
        hdr = view.tableView.horizontalHeader()
        assert hdr is not None
        self.settings.setValue("sortColumn", hdr.sortIndicatorSection())
        self.settings.setValue("sortOrder", hdr.sortIndicatorOrder())
        self.settings.setValue("windowWidth", view.width())
        self.settings.setValue("windowHeight", view.height())

    def onCurrentRowChanged(
        self,
        current: QtCore.QModelIndex,
        previous: QtCore.QModelIndex,
    ) -> None:
        if previous.row() != -1:
            model = self._view.model
            index = model.index(
                sourceIndex(current).row(),
                Column.ReadState,
                current.parent(),
            )
            model.setReadState(index, Qt.CheckState.Checked)
        self.updateStatus()
        self.updateUnreadCount()

    def updateStatus(self) -> None:
        view = self._view
        text = "%i of %i elogs" % (self.currentRow() + 1, view.model.elogCount())
        view.statusLabel.setText(text)

    def updateUnreadCount(self) -> None:
        view = self._view
        text = "%i unread" % view.model.unreadCount()
        view.unreadLabel.setText(text)
        view.setWindowTitle("Elogviewer (%s)" % text)

    def currentRow(self) -> int:
        sm = self._view.tableView.selectionModel()
        assert sm is not None
        return sm.currentIndex().row()

    def rowCount(self) -> int:
        return self._view.proxyModel.rowCount()

    def setSelectedReadState(self, state: Qt.CheckState) -> None:
        sm = self._view.tableView.selectionModel()
        assert sm is not None
        rows = sm.selectedRows(Column.ReadState)
        if not rows:
            return
        model = self._view.model
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
        sm = self._view.tableView.selectionModel()
        assert sm is not None
        rows = sm.selectedRows(Column.ImportantState)
        if not rows:
            return
        model = self._view.model
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
        view = self._view
        sm = view.tableView.selectionModel()
        assert sm is not None
        selection = [view.proxyModel.mapToSource(idx) for idx in sm.selectedRows()]
        selection.sort(key=lambda idx: idx.row())
        # Avoid call to onCurrentRowChanged() by clearing
        # selection with reset().
        currentRow = self.currentRow()
        sm.reset()

        filename: Path | None = None
        try:
            for index in reversed(selection):
                filename = view.model.itemFromIndex(index).filename()
                if filename.exists():
                    filename.unlink()
                view.model.removeRow(index.row())
        except OSError as exc:
            QtWidgets.QMessageBox.critical(
                view,
                "Error",
                f"Error while trying to delete '{filename}':<br><b>{exc.strerror}</b>",
            )

        view.tableView.selectRow(min(currentRow, self.rowCount() - 1))
        self.updateStatus()

    def populate(self) -> None:
        view = self._view
        currentRow = self.currentRow()
        sm = view.tableView.selectionModel()
        assert sm is not None
        sm.reset()
        view.model.populate(
            (
                Path(f)
                for f in itertools.chain(
                    glob.iglob(str(self.config.elogpath / "*:*:*.log*")),
                    glob.iglob(str(self.config.elogpath / "*" / "*:*.log*")),
                )
            ),
            settings=StateStore(self.settings),
        )
        view.tableView.selectRow(min(currentRow, self.rowCount() - 1))
