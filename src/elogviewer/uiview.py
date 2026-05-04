# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import glob
import itertools
from contextlib import AbstractContextManager
from functools import partial
from pathlib import Path
from typing import IO, Final, Protocol, override

from PyQt6 import QtCore, QtGui, QtWidgets

from .__version__ import __version__
from .eclass import EClass
from .model import Column, ElogModelItem
from .parser import ColorStrategy, ParserFSM
from .uimodel import Model, Role

Qt = QtCore.Qt


def _sourceIndex(index: QtCore.QModelIndex) -> QtCore.QModelIndex:
    model = index.model()
    if not model:
        return index
    return model.mapToSource(index)


def _itemFromIndex(index: QtCore.QModelIndex) -> ElogModelItem:
    assert index.isValid()
    sourceIndex = _sourceIndex(index)
    model = sourceIndex.model()
    assert isinstance(model, Model)
    return model.itemFromIndex(sourceIndex)


def makeHtml(
    file: AbstractContextManager[IO[str]], *, colorStrategy: ColorStrategy
) -> str:
    parsed = []
    with ParserFSM(parsed, colorStrategy=colorStrategy) as parser, file as f:
        for line in f:
            parser.parse(line)
    return "\n".join(_ for _ in parsed if _ is not None)


def eclassColor(eclass: EClass) -> tuple[int, int, int]:
    return {
        EClass.Error: (0xFF, 0x00, 0x00),
        EClass.Warning: (0xE5, 0x67, 0x17),
        EClass.Log: (0x00, 0x80, 0x00),
        EClass.Info: (0x00, 0x80, 0x00),
        EClass.QA: (0x00, 0x80, 0x00),
    }[eclass]


class TextToHtmlDelegate(QtWidgets.QItemDelegate):
    @override
    def __repr__(self) -> str:
        return f"elogviewer.{self.__class__.__name__}({self.parent()!r})"

    @override
    def setEditorData(
        self,
        editor: QtWidgets.QWidget | None,
        index: QtCore.QModelIndex,
    ) -> None:
        if not index.isValid() or not isinstance(editor, QtWidgets.QTextEdit):
            return
        model = index.model()
        assert isinstance(model, Model)
        item = model.itemFromIndex(index)
        header = f"<h2>{item.category()}/{item.package()}</h2>"
        editor.setHtml(header + makeHtml(item.file(), colorStrategy=eclassColor))


class SeverityColorDelegate(QtWidgets.QStyledItemDelegate):
    @override
    def paint(
        self,
        painter: QtGui.QPainter | None,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        if not index.isValid():
            return
        self.initStyleOption(option, index)
        if option.text is None:
            return super().paint(painter, option, index)
        try:
            color = QtGui.QColor(*eclassColor(EClass[option.text]))
        except KeyError:
            pass
        else:
            option.palette.setColor(QtGui.QPalette.ColorRole.Text, color)
        super().paint(painter, option, index)


class ReadFontStyleDelegate(QtWidgets.QStyledItemDelegate):
    @override
    def paint(
        self,
        painter: QtGui.QPainter | None,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        if not index.isValid():
            return
        self.initStyleOption(option, index)
        option.font.setBold(not _itemFromIndex(index).isReadState())
        super().paint(painter, option, index)


class ButtonDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(
        self,
        checked: str,
        unchecked: str,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._checked = checked
        self._unchecked = unchecked

    @override
    def initStyleOption(
        self,
        option: QtWidgets.QStyleOptionViewItem | None,
        index: QtCore.QModelIndex,
    ) -> None:
        super().initStyleOption(option, index)
        if option is None:
            return
        option.features &= (
            ~QtWidgets.QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        )
        option.text = (
            self._checked
            if bool(index.data(role=Qt.ItemDataRole.CheckStateRole))
            else self._unchecked
        )
        option.displayAlignment = Qt.AlignmentFlag.AlignCenter
        option.font.setFamilies(
            ["Noto Sans Symbols", "Symbola", "DejaVu Sans", option.font.family()]
        )

    @override
    def paint(
        self,
        painter: QtGui.QPainter | None,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        if not index.isValid():
            return
        self.initStyleOption(option, index)
        widget = self.parent()
        assert isinstance(widget, QtWidgets.QWidget)
        style = widget.style() or QtWidgets.QApplication.style()
        assert style is not None
        style.drawControl(
            QtWidgets.QStyle.ControlElement.CE_ItemViewItem, option, painter, widget
        )

    @override
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
            index.flags() & Qt.ItemFlag.ItemIsUserCheckable
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
            current = index.data(role=Qt.ItemDataRole.CheckStateRole)
            new_state = (
                Qt.CheckState.Unchecked if bool(current) else Qt.CheckState.Checked
            )
            model.setData(index, new_state, Qt.ItemDataRole.CheckStateRole)
            return True
        return False


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
    def elogpath(self) -> Path: ...


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
        horizontalHeader.sortIndicatorChanged.connect(
            lambda column, order: self.proxyModel.sort(column, order)
        )

        for column, delegate in (
            (Column.ImportantState, ButtonDelegate("★", "☆", self.tableView)),
            (Column.ReadState, ButtonDelegate("●", "○", self.tableView)),
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
        self.refreshAction = QtGui.QAction(
            iconFromTheme("view-refresh"),
            "Refresh",
            self.toolBar,
        )
        self.refreshAction.setShortcut(QtGui.QKeySequence.StandardKey.Refresh)
        self.refreshAction.triggered.connect(self.populate)
        self.markReadAction = QtGui.QAction(
            iconFromTheme("mail-mark-read"),
            "Mark read",
            self.toolBar,
        )
        self.markReadAction.triggered.connect(
            partial(self.setSelectedReadState, Qt.CheckState.Checked)
        )
        self.markUnreadAction = QtGui.QAction(
            iconFromTheme("mail-mark-unread"),
            "Mark unread",
            self.toolBar,
        )
        self.markUnreadAction.triggered.connect(
            partial(self.setSelectedReadState, Qt.CheckState.Unchecked)
        )
        self.toggleImportantAction = QtGui.QAction(
            iconFromTheme("mail-mark-important"),
            "Important",
            self.toolBar,
        )
        self.toggleImportantAction.triggered.connect(self.toggleSelectedImportantState)
        self.deleteAction = QtGui.QAction(
            iconFromTheme("edit-delete"),
            "Delete",
            self.toolBar,
        )
        self.deleteAction.setShortcut(QtGui.QKeySequence.StandardKey.Delete)
        self.deleteAction.triggered.connect(self.deleteSelected)
        self.aboutAction = QtGui.QAction(
            iconFromTheme("help-about"),
            "About",
            self.toolBar,
        )
        self.aboutAction.setShortcut(QtGui.QKeySequence.StandardKey.HelpContents)
        self.aboutAction.triggered.connect(
            partial(
                QtWidgets.QMessageBox.about,
                self,
                "About (k)elogviewer",
                (
                    f"<h1>(k)elogviewer {__version__}</h1>"
                    + "<br>".join(
                        [
                            "(k)elogviewer, copyright (c) 2007-2016 Mathias Laurin",
                            "kelogviewer, copyright (c) 2007 Jeremy Wickersheimer",
                            "GNU General Public License (GPL) version 2"
                            + "<a href=http://sourceforge.net/projects/elogviewer>"
                            + "http://sourceforge.net/projects/elogviewer</a>",
                        ]
                    )
                    + "<h2>Written by</h2>"
                    + "<br>".join(
                        [
                            "Mathias Laurin (current maintainer)",
                            "Timothy Kilbourn (initial author)",
                            "Jeremy Wickersheimer (qt3/KDE port)",
                            "David Radice, gentoo bug #187595",
                            "Christian Faulhammer, gentoo bug #192701",
                            "Fonic (<a href=https://github.com/fonic>github.com/fonic</a>),"
                            + "github issues 2-3, 6-8",
                        ]
                    )
                    + "<h2>Documented by</h2>"
                    + "Christian Faulhammer"
                    + '<a href="mailto:opfer@gentoo.org">&lt;opfer@gentoo.org&gt;</a>'
                ),
            ),
        )
        self.exitAction = QtGui.QAction(
            iconFromTheme("application-exit"),
            "Quit",
            self.toolBar,
        )
        self.exitAction.setShortcut(QtGui.QKeySequence.StandardKey.Quit)
        self.exitAction.triggered.connect(self.close)
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
        self.model.save(StateStore(self.settings))
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
        text = "%i of %i elogs" % (self.currentRow() + 1, self.model.elogCount())
        self.statusLabel.setText(text)

    def updateUnreadCount(self) -> None:
        text = "%i unread" % self.model.unreadCount()
        self.unreadLabel.setText(text)
        self.setWindowTitle("Elogviewer (%s)" % text)

    def currentRow(self) -> int:
        sm = self.tableView.selectionModel()
        assert sm is not None
        return sm.currentIndex().row()

    def rowCount(self) -> int:
        return self.proxyModel.rowCount()

    def setSelectedReadState(self, state: Qt.CheckState) -> None:
        sm = self.tableView.selectionModel()
        assert sm is not None
        rows = sm.selectedRows(Column.ReadState)
        if not rows:
            return
        self.model.blockSignals(True)
        try:
            for index in rows:
                self.model.setReadState(_sourceIndex(index), state)
        finally:
            self.model.blockSignals(False)
        self.model.dataChanged.emit(
            self.model.index(0, 0),
            self.model.index(self.model.rowCount() - 1, self.model.columnCount() - 1),
        )
        self.updateUnreadCount()

    def toggleSelectedImportantState(self) -> None:
        sm = self.tableView.selectionModel()
        assert sm is not None
        rows = sm.selectedRows(Column.ImportantState)
        if not rows:
            return
        firstSourceIndex = _sourceIndex(rows[0])
        state = (
            Qt.CheckState.Unchecked
            if self.model.importantState(firstSourceIndex) is Qt.CheckState.Checked
            else Qt.CheckState.Checked
        )
        self.model.blockSignals(True)
        try:
            for index in rows:
                self.model.setImportantState(_sourceIndex(index), state)
        finally:
            self.model.blockSignals(False)
        self.model.dataChanged.emit(
            self.model.index(0, Column.ImportantState),
            self.model.index(self.model.rowCount() - 1, Column.ImportantState),
        )

    def deleteSelected(self) -> None:
        sm = self.tableView.selectionModel()
        assert sm is not None
        selection = [self.proxyModel.mapToSource(idx) for idx in sm.selectedRows()]
        selection.sort(key=lambda idx: idx.row())
        # Avoid call to onCurrentRowChanged() by clearing
        # selection with reset().
        currentRow = self.currentRow()
        sm.reset()

        filename: Path | None = None
        try:
            for index in reversed(selection):
                filename = self.model.itemFromIndex(index).filename()
                if filename.exists():
                    filename.unlink()
                self.model.removeRow(index.row())
        except OSError as exc:
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                f"Error while trying to delete '{filename}':<br><b>{exc.strerror}</b>",
            )

        self.tableView.selectRow(min(currentRow, self.rowCount() - 1))
        self.updateStatus()

    def populate(self) -> None:
        currentRow = self.currentRow()
        sm = self.tableView.selectionModel()
        assert sm is not None
        sm.reset()
        self.model.populate(
            (
                Path(f)
                for f in itertools.chain(
                    glob.iglob(str(self.config.elogpath / "*:*:*.log*")),
                    glob.iglob(str(self.config.elogpath / "*" / "*:*.log*")),
                )
            ),
            settings=StateStore(self.settings),
        )
        self.tableView.selectRow(min(currentRow, self.rowCount() - 1))
