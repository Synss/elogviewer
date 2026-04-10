# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import glob
import itertools
import os
from contextlib import suppress
from functools import partial
from math import cos, sin
from typing import Protocol

from PyQt6 import QtCore, QtGui, QtWidgets

from .__version__ import __version__
from .eclass import EClass
from .elog import Elog
from .uimodel import Column, ElogModelItem, Model, Role

Qt = QtCore.Qt


def _sourceIndex(index: QtCore.QModelIndex) -> QtCore.QModelIndex:
    model = index.model()
    with suppress(AttributeError):
        index = model.mapToSource(index)  # type: ignore  # proxy
    return index


def _itemFromIndex(index: QtCore.QModelIndex) -> ElogModelItem:
    assert index.isValid()
    model = _sourceIndex(index).model()
    assert isinstance(model, Model)
    return model.itemFromIndex(index)


def eclassColor(eclass: EClass) -> tuple[int, int, int]:
    return {
        EClass.Error: (0xFF, 0x00, 0x00),
        EClass.Warning: (0xE5, 0x67, 0x17),
        EClass.Log: (0x00, 0x80, 0x00),
        EClass.Info: (0x00, 0x80, 0x00),
        EClass.QA: (0x00, 0x80, 0x00),
    }[eclass]


class TextToHtmlDelegate(QtWidgets.QItemDelegate):
    def __repr__(self) -> str:
        return f"elogviewer.{self.__class__.__name__}({self.parent()!r})"

    def setEditorData(
        self,
        editor: QtWidgets.QWidget | None,
        index: QtCore.QModelIndex,
    ) -> None:
        if not index.isValid() or not isinstance(editor, QtWidgets.QTextEdit):
            return
        model = index.model()
        assert isinstance(model, Model)
        editor.setHtml(model.itemFromIndex(index).html(colorStrategy=eclassColor))


class SeverityColorDelegate(QtWidgets.QStyledItemDelegate):
    def paint(
        self,
        painter: QtGui.QPainter | None,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        if not index.isValid():
            return
        self.initStyleOption(option, index)
        try:
            color = QtGui.QColor(eclassColor(EClass[option.text]))
        except KeyError:
            pass
        else:
            option.palette.setColor(QtGui.QPalette.ColorRole.Text, color)
        super().paint(painter, option, index)


class ReadFontStyleDelegate(QtWidgets.QStyledItemDelegate):
    def paint(
        self,
        painter: QtGui.QPainter | None,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        if not index.isValid():
            return
        self.initStyleOption(option, index)
        option.font.setBold(
            _itemFromIndex(index).readState() == Qt.CheckState.Unchecked,
        )
        super().paint(painter, option, index)


class Bullet(QtWidgets.QAbstractButton):
    _scaleFactor = 20

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setCheckable(True)

    def paintEvent(self, e: QtGui.QPaintEvent | None) -> None:
        assert e is not None
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        green = QtGui.QBrush(QtGui.QColorConstants.DarkGreen)
        painter.setBrush(self.palette().dark() if self.isChecked() else green)
        rect = e.rect()
        painter.translate(rect.x(), rect.y())
        painter.scale(self._scaleFactor, self._scaleFactor)
        painter.drawEllipse(QtCore.QRectF(0.5, 0.5, 0.5, 0.5))

    def sizeHint(self) -> QtCore.QSize:
        return self._scaleFactor * QtCore.QSize(1, 1)


class Star(QtWidgets.QAbstractButton):
    # Largely inspired by Nokia's stardelegate example.

    _scaleFactor = 20

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setCheckable(True)
        self._starPolygon = QtGui.QPolygonF([QtCore.QPointF(1.0, 0.5)])
        for i in range(5):
            self._starPolygon.append(
                QtCore.QPointF(
                    0.5 + 0.5 * cos(0.8 * i * 3.14),
                    0.5 + 0.5 * sin(0.8 * i * 3.14),
                ),
            )

    def paintEvent(self, e: QtGui.QPaintEvent | None) -> None:
        assert e is not None
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        red = QtGui.QBrush(QtGui.QColorConstants.Red)
        painter.setBrush(red if self.isChecked() else self.palette().dark())
        rect = e.rect()
        yOffset = (rect.height() - self._scaleFactor) / 2.0
        painter.translate(rect.x(), rect.y() + yOffset)
        painter.scale(self._scaleFactor, self._scaleFactor)
        painter.drawPolygon(self._starPolygon, Qt.FillRule.WindingFill)

    def sizeHint(self) -> QtCore.QSize:
        return self._scaleFactor * QtCore.QSize(1, 1)


class ButtonDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(
        self,
        button: QtWidgets.QAbstractButton | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._btn = QtWidgets.QPushButton() if button is None else button
        self._btn.setCheckable(True)
        self._btn.setParent(parent)
        self._btn.hide()

    def __repr__(self) -> str:
        return f"elogviewer.{self.__class__.__name__}(button={self._btn!r}, parent={self.parent()!r})"

    def sizeHint(
        self,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> QtCore.QSize:
        return super().sizeHint(option, index)

    def createEditor(
        self,
        parent: QtWidgets.QWidget | None,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> QtWidgets.QWidget | None:
        return None

    def setModelData(
        self,
        editor: QtWidgets.QWidget | None,
        model: QtCore.QAbstractItemModel | None,
        index: QtCore.QModelIndex,
    ) -> None:
        assert editor is not None and model is not None
        data = Qt.CheckState.Checked if editor.isChecked() else Qt.CheckState.Unchecked  # type: ignore
        model.setData(index, data, role=Qt.ItemDataRole.CheckStateRole)

    def paint(
        self,
        painter: QtGui.QPainter | None,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        assert painter is not None
        self._btn.setChecked(
            index.data(role=Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked,
        )
        self._btn.setGeometry(option.rect)
        if option.state & QtWidgets.QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        pixmap = self._btn.grab()
        painter.drawPixmap(option.rect.x(), option.rect.y(), pixmap)

    def editorEvent(
        self,
        event: QtCore.QEvent | None,
        model: QtCore.QAbstractItemModel | None,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> bool:
        if event is None or model is None:
            return False
        if (
            index.flags() & Qt.ItemFlag.ItemIsEditable
            and (
                event.type()
                in (
                    QtCore.QEvent.Type.MouseButtonRelease,
                    QtCore.QEvent.Type.MouseButtonDblClick,
                )
                and isinstance(event, QtGui.QMouseEvent)
                and event.button() == Qt.MouseButton.LeftButton
            )
        ) or (
            event.type() == QtCore.QEvent.Type.KeyPress
            and isinstance(event, QtGui.QKeyEvent)
            and event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Select)
        ):
            self._btn.toggle()
            self.setModelData(self._btn, model, index)
            self.commitData.emit(self._btn)
            return True
        return False


class ElogviewerUi(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        centralWidget = QtWidgets.QWidget(self)
        centralLayout = QtWidgets.QVBoxLayout()
        centralWidget.setLayout(centralLayout)
        self.setCentralWidget(centralWidget)

        self.tableView = QtWidgets.QTableView(centralWidget)
        self.tableView.setSortingEnabled(True)
        self.tableView.setSelectionMode(self.tableView.SelectionMode.ExtendedSelection)
        self.tableView.setSelectionBehavior(self.tableView.SelectionBehavior.SelectRows)
        horizontalHeader = self.tableView.horizontalHeader()
        assert horizontalHeader is not None
        horizontalHeader.setSectionsClickable(True)
        horizontalHeader.setSectionResizeMode(
            horizontalHeader.ResizeMode.ResizeToContents,
        )
        horizontalHeader.setStretchLastSection(True)
        verticalHeader = self.tableView.verticalHeader()
        assert verticalHeader is not None
        verticalHeader.hide()
        centralLayout.addWidget(self.tableView)

        self.textEdit = QtWidgets.QTextBrowser(centralWidget)
        self.textEdit.setOpenExternalLinks(True)
        self.textEdit.setText("""No elog selected.""")
        centralLayout.addWidget(self.textEdit)

        self.toolBar = QtWidgets.QToolBar(self)
        self.addToolBar(self.toolBar)

        statusBar = self.statusBar()
        assert statusBar is not None
        self.statusLabel = QtWidgets.QLabel(statusBar)
        statusBar.addWidget(self.statusLabel)
        self.unreadLabel = QtWidgets.QLabel(statusBar)
        statusBar.addWidget(self.unreadLabel)


class _Config(Protocol):
    @property
    def elogpath(self) -> str | os.PathLike[str]: ...


class Elogviewer(ElogviewerUi):
    def __init__(self, config: _Config) -> None:
        super().__init__()
        self.config = config
        self.settings = QtCore.QSettings("elogviewer", "elogviewer")
        if not self.settings.contains("readFlag"):
            self.settings.setValue("readFlag", set())
        if not self.settings.contains("importantFlag"):
            self.settings.setValue("importantFlag", set())
        if self.settings.contains("windowWidth") and self.settings.contains(
            "windowHeight",
        ):
            self.resize(
                int(self.settings.value("windowWidth")),
                int(self.settings.value("windowHeight")),
            )
        else:
            primaryScreen = QtWidgets.QApplication.primaryScreen()
            assert primaryScreen is not None  # FIXME properly
            screenSize = primaryScreen.availableGeometry()
            self.resize(screenSize.width() // 2, screenSize.height() // 2)

        self.model = Model(self.tableView)
        self.model.dataChanged.connect(self.saveSettings)
        self.proxyModel = QtCore.QSortFilterProxyModel(self.tableView)
        self.proxyModel.setFilterKeyColumn(Column.Package)
        self.proxyModel.setSortRole(Role.SortRole)
        self.proxyModel.setSourceModel(self.model)
        self.tableView.setModel(self.proxyModel)

        horizontalHeader = self.tableView.horizontalHeader()
        assert horizontalHeader is not None
        horizontalHeader.sortIndicatorChanged.connect(self.proxyModel.sort)

        for column, delegate in (
            (Column.ImportantState, ButtonDelegate(Star(), self.tableView)),
            (Column.ReadState, ButtonDelegate(Bullet(), self.tableView)),
            (Column.Eclass, SeverityColorDelegate(self.tableView)),
        ):
            self.tableView.setItemDelegateForColumn(column, delegate)
        self.tableView.setItemDelegate(ReadFontStyleDelegate(self.tableView))

        self.textEditMapper = QtWidgets.QDataWidgetMapper(self.tableView)
        self.textEditMapper.setSubmitPolicy(self.textEditMapper.SubmitPolicy.AutoSubmit)
        self.textEditMapper.setItemDelegate(TextToHtmlDelegate(self.textEditMapper))
        self.textEditMapper.setModel(self.model)
        self.textEditMapper.addMapping(self.textEdit, 0)
        selectionModel = self.tableView.selectionModel()
        assert selectionModel is not None
        selectionModel.currentRowChanged.connect(
            lambda curr, prev: self.textEditMapper.setCurrentModelIndex(
                _sourceIndex(curr),
            ),
        )

        iconFromTheme = QtGui.QIcon.fromTheme
        self.refreshAction = QtGui.QAction(  # type: ignore
            iconFromTheme("view-refresh"),
            "Refresh",
            self.toolBar,
            shortcut=QtGui.QKeySequence.StandardKey.Refresh,
            triggered=self.populate,
        )
        self.markReadAction = QtGui.QAction(  # type: ignore
            iconFromTheme("mail-mark-read"),
            "Mark read",
            self.toolBar,
            triggered=partial(self.setSelectedReadState, Qt.CheckState.Checked),
        )
        self.markUnreadAction = QtGui.QAction(  # type: ignore
            iconFromTheme("mail-mark-unread"),
            "Mark unread",
            self.toolBar,
            triggered=partial(self.setSelectedReadState, Qt.CheckState.Unchecked),
        )
        self.toggleImportantAction = QtGui.QAction(  # type: ignore
            iconFromTheme("mail-mark-important"),
            "Important",
            self.toolBar,
            triggered=self.toggleSelectedImportantState,
        )
        self.deleteAction = QtGui.QAction(  # type: ignore
            iconFromTheme("edit-delete"),
            "Delete",
            self.toolBar,
            shortcut=QtGui.QKeySequence.StandardKey.Delete,
            triggered=self.deleteSelected,
        )
        self.aboutAction = QtGui.QAction(  # type: ignore
            iconFromTheme("help-about"),
            "About",
            self.toolBar,
            shortcut=QtGui.QKeySequence.StandardKey.HelpContents,
            triggered=partial(
                QtWidgets.QMessageBox.about,
                self,
                "About (k)elogviewer",
                "<h1>(k)elogviewer %s</h1>"
                "(k)elogviewer, copyright (c) 2007-2016 Mathias Laurin<br>"
                "kelogviewer, copyright (c) 2007 Jeremy Wickersheimer<br>"
                "GNU General Public License (GPL) version 2<br>"
                "<a href=http://sourceforge.net/projects/elogviewer>"
                "http://sourceforge.net/projects/elogviewer</a>"
                "<h2>Written by</h2>"
                "Mathias Laurin (current maintainer)<br>"
                "Timothy Kilbourn (initial author)<br>"
                "Jeremy Wickersheimer (qt3/KDE port)<br>"
                "David Radice, gentoo bug #187595<br>"
                "Christian Faulhammer, gentoo bug #192701<br>"
                "Fonic (<a href=https://github.com/fonic>github.com/fonic</a>),"
                "github issues 2-3, 6-8<br>"
                "<h2>Documented by</h2>"
                "Christian Faulhammer"
                '<a href="mailto:opfer@gentoo.org">&lt;opfer@gentoo.org&gt;</a>'
                % __version__,
            ),
        )
        self.exitAction = QtGui.QAction(  # type: ignore
            iconFromTheme("application-exit"),
            "Quit",
            self.toolBar,
            shortcut=QtGui.QKeySequence.StandardKey.Quit,
            triggered=self.close,
        )
        self.toolBar.addAction(self.refreshAction)
        self.toolBar.addAction(self.markReadAction)
        self.toolBar.addAction(self.markUnreadAction)
        self.toolBar.addAction(self.toggleImportantAction)
        self.toolBar.addAction(self.deleteAction)
        self.toolBar.addAction(self.aboutAction)
        self.toolBar.addAction(self.exitAction)

        def fromToolBar(name: str) -> QtWidgets.QWidget | None:
            action = getattr(self, "%sAction" % name)
            return self.toolBar.widgetForAction(action)

        self.refreshButton = fromToolBar("refresh")
        self.markReadButton = fromToolBar("markRead")
        self.markUnreadButton = fromToolBar("markUnread")
        self.toggleImportantButton = fromToolBar("toggleImportant")
        self.deleteButton = fromToolBar("delete")
        self.aboutButton = fromToolBar("about")

        selectionModel2 = self.tableView.selectionModel()
        assert selectionModel2 is not None
        selectionModel2.currentRowChanged.connect(self.onCurrentRowChanged)

        self.searchLineEdit = QtWidgets.QLineEdit(self.toolBar)
        self.searchLineEdit.setPlaceholderText("search")
        self.searchLineEdit.textEdited.connect(
            self.proxyModel.setFilterRegularExpression,
        )
        self.toolBar.addWidget(self.searchLineEdit)

        QtCore.QTimer.singleShot(100, self.populate)
        if self.settings.contains("sortColumn") and self.settings.contains("sortOrder"):
            self.tableView.sortByColumn(
                int(self.settings.value("sortColumn")),
                (
                    Qt.SortOrder.DescendingOrder
                    if self.settings.value("sortOrder") == 1
                    else Qt.SortOrder.AscendingOrder
                ),
            )
        else:
            self.tableView.sortByColumn(Column.Date, Qt.SortOrder.DescendingOrder)
        self.tableView.selectRow(0)

    def saveSettings(self) -> None:
        readFlag = set()
        importantFlag = set()
        for row in range(self.model.rowCount()):
            item = self.model.item(row, Column.ReadState)
            if item.readState() == Qt.CheckState.Checked:
                readFlag.add(item.filename())
            if item.importantState() == Qt.CheckState.Checked:
                importantFlag.add(item.filename())
        self.settings.setValue("readFlag", readFlag)
        self.settings.setValue("importantFlag", importantFlag)
        hdr = self.tableView.horizontalHeader()
        assert hdr is not None
        self.settings.setValue("sortColumn", hdr.sortIndicatorSection())
        self.settings.setValue("sortOrder", hdr.sortIndicatorOrder())
        self.settings.setValue("windowWidth", self.width())
        self.settings.setValue("windowHeight", self.height())

    def onCurrentRowChanged(
        self,
        current: QtCore.QModelIndex,
        previous: QtCore.QModelIndex,
    ) -> None:
        if previous.row() != -1:
            index = self.model.index(
                _sourceIndex(current).row(),
                Column.ReadState,
                current.parent(),
            )
            self.model.setReadState(index, Qt.CheckState.Checked)
        self.updateStatus()
        self.updateUnreadCount()

    def updateStatus(self) -> None:
        text = "%i of %i elogs" % (self.currentRow() + 1, self.elogCount())
        self.statusLabel.setText(text)

    def updateUnreadCount(self) -> None:
        text = "%i unread" % self.unreadCount()
        self.unreadLabel.setText(text)
        self.setWindowTitle("Elogviewer (%s)" % text)

    def currentRow(self) -> int:
        sm = self.tableView.selectionModel()
        assert sm is not None
        return sm.currentIndex().row()

    def rowCount(self) -> int:
        return self.proxyModel.rowCount()

    def elogCount(self) -> int:
        return self.model.rowCount()

    def readCount(self) -> int:
        count = 0
        for row in range(self.model.rowCount()):
            if self.model.item(row).isReadState():
                count += 1
        return count

    def unreadCount(self) -> int:
        return self.elogCount() - self.readCount()

    def importantCount(self) -> int:
        count = 0
        for row in range(self.model.rowCount()):
            if self.model.item(row).isImportantState():
                count += 1
        return count

    def setSelectedReadState(self, state: Qt.CheckState) -> None:
        sm = self.tableView.selectionModel()
        assert sm is not None
        for index in sm.selectedIndexes():
            self.model.setReadState(_sourceIndex(index), state)
        self.updateUnreadCount()

    def toggleSelectedImportantState(self) -> None:
        sm = self.tableView.selectionModel()
        assert sm is not None
        state: Qt.CheckState | None = None
        for index in sm.selectedRows(Column.ImportantState):
            sourceIndex = _sourceIndex(index)
            if state is None:
                state = (
                    Qt.CheckState.Unchecked
                    if self.model.importantState(sourceIndex) is Qt.CheckState.Checked
                    else Qt.CheckState.Checked
                )
            self.model.setImportantState(sourceIndex, state)

    def deleteSelected(self) -> None:
        sm = self.tableView.selectionModel()
        assert sm is not None
        selection = [self.proxyModel.mapToSource(idx) for idx in sm.selectedRows()]
        selection.sort(key=lambda idx: idx.row())
        # Avoid call to onCurrentRowChanged() by clearing
        # selection with reset().
        currentRow = self.currentRow()
        sm.reset()

        try:
            for index in reversed(selection):
                filename = self.model.itemFromIndex(index).filename()
                if os.path.exists(filename):
                    os.remove(filename)
                self.model.removeRow(index.row())
        except OSError as exc:
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                "Error while trying to delete"
                "'%s':<br><b>%s</b>" % (filename, exc.strerror),
            )

        self.tableView.selectRow(min(currentRow, self.rowCount() - 1))
        self.updateStatus()

    def populate(self) -> None:
        currentRow = self.currentRow()
        sm = self.tableView.selectionModel()
        assert sm is not None
        sm.reset()
        self.model.removeRows(0, self.model.rowCount())
        self.model.beginResetModel()
        for filename in itertools.chain(
            glob.iglob(os.path.join(self.config.elogpath, "*:*:*.log*")),
            glob.iglob(os.path.join(self.config.elogpath, "*", "*:*.log*")),
        ):
            item = ElogModelItem(Elog.fromFilename(filename))
            item.setReadState(
                Qt.CheckState.Checked
                if filename in self.settings.value("readFlag")
                else Qt.CheckState.Unchecked,
            )
            item.setImportantState(
                Qt.CheckState.Checked
                if filename in self.settings.value("importantFlag")
                else Qt.CheckState.Unchecked,
            )
            self.model.appendItem(item)
        self.model.endResetModel()
        self.tableView.selectRow(min(currentRow, self.rowCount() - 1))
