#!/usr/bin/env python3
# (c) 2011, 2013, 2015 Mathias Laurin, GPL2
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
Elogviewer should help you not to miss important information.

You need to enable the elog feature by setting at least one of
PORTAGE_ELOG_CLASSES="info warn error log qa" and
PORTAGE_ELOG_SYSTEM="save" in /etc/make.conf.

You need to add yourself to the portage group to use elogviewer
without privileges.

Read /etc/make.conf.example for more information.
"""

import abc
import argparse
import bz2
import enum
import glob
import gzip
import io
import itertools
import locale
import logging
import os
import re
import sys
import time
import weakref
from collections import namedtuple
from contextlib import closing, suppress
from functools import partial
from math import cos, sin

from PyQt5 import QtCore, QtGui, QtWidgets

try:
    import portage
except ImportError:
    portage = None

__version__ = "3.0"


Qt = QtCore.Qt

_LOGGER = logging.getLogger("elogviewer")


class Role(enum.IntEnum):

    SortRole = Qt.UserRole + 1


class Column(enum.IntEnum):

    ImportantState = 0
    Category = 1
    Package = 2
    ReadState = 3
    Eclass = 4
    Date = 5


class EClass(str, enum.Enum):

    Error = "ERROR"
    Warning = "WARN"
    Log = "LOG"
    Info = "INFO"
    QA = "QA"

    def color(self):
        return {
            "Error": QtGui.QColor(Qt.red),
            "Warning": QtGui.QColor(229, 103, 23),
            "Log": QtGui.QColor(Qt.darkGreen),
            "Info": QtGui.QColor(Qt.darkGreen),
            "QA": QtGui.QColor(Qt.darkGreen),
        }[self.name]

    def htmlColor(self):
        return self.color().name()


class Elog(namedtuple("Elog", ["filename", "category", "package", "date", "eclass"])):
    HeaderPattern = re.compile(
        r"({}):\s+(\S+)".format("|".join(_.value for _ in EClass))
    )
    AnsiColorPattern = re.compile(r"\x1b\[[0-9;]+m")
    LinkPattern = re.compile(r"((https?|ftp)://\S+)", re.IGNORECASE)
    BugPattern = re.compile(r"([bB]ug)\s+#([0-9]+)", re.IGNORECASE)
    PackagePattern = re.compile(r"([a-z0-9]+-[a-z0-9]+/[a-z0-9]+)-([0-9.]+)", re.IGNORECASE)

    @staticmethod
    def __file(filename):
        # Static so that it may be called *before* instantiation.
        _, ext = os.path.splitext(filename)
        try:
            return {".gz": gzip.open, ".bz2": bz2.BZ2File, ".log": open}[ext](
                filename, "rt"
            )
        except KeyError:
            _LOGGER.error("%s: unsupported format", filename)
            return closing(
                io.StringIO(
                    """
                    <!-- set eclass: ERROR: -->
                    <h2>Unsupported format</h2>
                    The selected elog is in an unsupported format.
                    """
                )
            )
        except FileNotFoundError:
            _LOGGER.error("%s: file not found", filename)
            return closing(
                io.StringIO(
                    """
                    <!-- set eclass: ERROR: -->
                    <h2>File not found</h2>
                    The selected elog could does not exist on the filesystem.
                    """
                )
            )
        except IOError:
            _LOGGER.error("%s: could not open file", filename)
            return closing(
                io.StringIO(
                    """
                    <!-- set eclass: ERROR: -->
                    <h2>File does not open</h2>
                    The selected elog could not be opened.
                    """
                )
            )

    @property
    def file(self):
        return self.__file(self.filename)

    @classmethod
    def fromFilename(cls, filename):
        _LOGGER.debug(filename)
        basename = os.path.basename(filename)
        try:
            category, package, rest = basename.split(":")
        except ValueError:
            category = os.path.dirname(filename).split(os.sep)[-1]
            package, rest = basename.split(":")
        date = rest.split(".")[0]
        date = time.strptime(date, "%Y%m%d-%H%M%S")
        with cls.__file(filename) as elogFile:
            eclass = cls.getClass(elogFile.read())
        return cls(filename, category, package, date, eclass)

    @classmethod
    def getClass(cls, elogBody):
        # Get the highest elog class. Adapted from Luca Marturana's elogv.
        eClasses = frozenset(_[0] for _ in cls.HeaderPattern.findall(elogBody))
        for eClass in EClass:
            if eClass.value in eClasses:
                return eClass
        _LOGGER.error("elog has no identifiable eclass")
        return EClass.Log

    @property
    def contents(self):
        with self.file as file:
            return file.read()

    @property
    def html(self):
        parsed = []
        with ParserFSM(parsed) as parser, self.file as file:
            for line in file:
                parser.parse(line)
        return os.linesep.join(_ for _ in parsed if _ is not None)


def _sourceIndex(index):
    model = index.model()
    with suppress(AttributeError):
        index = model.mapToSource(index)  # proxy
    return index


def _itemFromIndex(index):
    if index.isValid():
        index = _sourceIndex(index)
        return index.model().itemFromIndex(index)
    return QtGui.QStandardItem()


class TextToHtmlDelegate(QtWidgets.QItemDelegate):
    def __repr__(self):
        return "elogviewer.%s(%r)" % (self.__class__.__name__, self.parent())

    def setEditorData(self, editor, index):
        if not index.isValid() or not isinstance(editor, QtWidgets.QTextEdit):
            return
        model = index.model()
        editor.setHtml(model.itemFromIndex(index).html())


class AbstractState(abc.ABC):
    def __init__(self, context):
        self.context = weakref.proxy(context)

    @abc.abstractmethod
    def enter(self):
        """Entry action."""

    @abc.abstractmethod
    def exit(self):
        """Exit action."""

    @abc.abstractmethod
    def parse(self, line):
        """Do action."""


class NoopState(AbstractState):
    def enter(self):
        pass

    def exit(self):
        pass

    def parse(self, line):
        return line


class HeaderState(AbstractState):
    def enter(self):
        return "<h2>"

    def exit(self):
        return "</h2>"

    def parse(self, line):
        eclass, stage = line.split(":")
        self.context.eclass = {
            "ERROR": EClass.Error,
            "WARN": EClass.Warning,
            "LOG": EClass.Log,
            "INFO": EClass.Info,
            "QA": EClass.QA,
        }[eclass]
        return "{}: {}".format(self.context.eclass.name, stage)


class BodyState(AbstractState):
    __href = r'<a href="{url}">{text}</a>'
    _parse_link = partial(Elog.LinkPattern.sub, __href.format(url=r"\1", text=r"\1"))
    _parse_bug = partial(
        Elog.BugPattern.sub,
        __href.format(url=r"https://bugs.gentoo.org/\2", text=r"\1 #\2"),
    )
    _parse_pkg = partial(
        Elog.PackagePattern.sub,
        __href.format(url=r"http://packages.gentoo.org/packages/\1", text=r"\1-\2"),
    )
    _parse_ansi_colors = partial(Elog.AnsiColorPattern.sub, "")

    def enter(self):
        return '<p style="color: {}">'.format(self.context.eclass.htmlColor())

    def exit(self):
        return "</p>"

    def parse(self, line):
        line = self._parse_ansi_colors(line)
        line = self._parse_link(line)
        line = self._parse_bug(line)
        line = self._parse_pkg(line)
        return "{} <br />".format(line)


class ParserFSM:
    def __init__(self, results):
        self.eclass = EClass.Log
        self._results = results
        self._noopState = NoopState(self)
        self._headerState = HeaderState(self)
        self._bodyState = BodyState(self)

    @property
    def state(self):
        return self.__dict__.get("state", self._noopState)

    @state.setter
    def state(self, state):
        if state is not self.state:
            self._results.append(self.state.exit())
            self.__dict__["state"] = state
            self._results.append(self.state.enter())

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        if any(exc_info):
            return False
        self.state = self._noopState
        return True

    def _stateFor(self, line):
        if Elog.HeaderPattern.match(line):
            return self._headerState
        return self._bodyState

    def parse(self, line):
        if not line.strip():
            return
        self.state = self._stateFor(line)
        self._results.append(self.state.parse(line))


class SeverityColorDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter, option, index):
        if not index.isValid():
            return
        self.initStyleOption(option, index)
        try:
            color = EClass[option.text].color()
        except KeyError:
            pass
        else:
            option.palette.setColor(QtGui.QPalette.Text, color)
        super().paint(painter, option, index)


class ReadFontStyleDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter, option, index):
        if not index.isValid():
            return
        self.initStyleOption(option, index)
        option.font.setBold(_itemFromIndex(index).readState() == Qt.Unchecked)
        super().paint(painter, option, index)


class Bullet(QtWidgets.QAbstractButton):

    _scaleFactor = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setCheckable(True)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        green = QtGui.QBrush(Qt.darkGreen)
        painter.setBrush(self.palette().dark() if self.isChecked() else green)
        rect = event.rect()
        painter.translate(rect.x(), rect.y())
        painter.scale(self._scaleFactor, self._scaleFactor)
        painter.drawEllipse(QtCore.QRectF(0.5, 0.5, 0.5, 0.5))

    def sizeHint(self):
        return self._scaleFactor * QtCore.QSize(1.0, 1.0)


class Star(QtWidgets.QAbstractButton):
    # Largely inspired by Nokia's stardelegate example.

    _scaleFactor = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setCheckable(True)
        self._starPolygon = QtGui.QPolygonF([QtCore.QPointF(1.0, 0.5)])
        for i in range(5):
            self._starPolygon.append(
                QtCore.QPointF(
                    0.5 + 0.5 * cos(0.8 * i * 3.14), 0.5 + 0.5 * sin(0.8 * i * 3.14)
                )
            )

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        red = QtGui.QBrush(Qt.red)
        painter.setBrush(red if self.isChecked() else self.palette().dark())
        rect = event.rect()
        yOffset = (rect.height() - self._scaleFactor) / 2.0
        painter.translate(rect.x(), rect.y() + yOffset)
        painter.scale(self._scaleFactor, self._scaleFactor)
        painter.drawPolygon(self._starPolygon, QtCore.Qt.WindingFill)

    def sizeHint(self):
        return self._scaleFactor * QtCore.QSize(1.0, 1.0)


class ButtonDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, button=None, parent=None):
        super().__init__(parent)
        self._btn = QtWidgets.QPushButton() if button is None else button
        self._btn.setCheckable(True)
        self._btn.setParent(parent)
        self._btn.hide()

    def __repr__(self):
        return "elogviewer.%s(button=%r, parent=%r)" % (
            self.__class__.__name__,
            self._btn,
            self.parent(),
        )

    def sizeHint(self, option, index):
        return super().sizeHint(option, index)

    def createEditor(self, _parent, _option, _index):
        return None

    def setModelData(self, editor, model, index):
        data = Qt.Checked if editor.isChecked() else Qt.Unchecked
        model.setData(index, data, role=Qt.CheckStateRole)

    def paint(self, painter, option, index):
        self._btn.setChecked(index.data(role=Qt.CheckStateRole))
        self._btn.setGeometry(option.rect)
        if option.state & QtWidgets.QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        pixmap = self._btn.grab()
        painter.drawPixmap(option.rect.x(), option.rect.y(), pixmap)

    def editorEvent(self, event, model, _option, index):
        if (
            int(index.flags()) & Qt.ItemIsEditable
            and (
                event.type()
                in (QtCore.QEvent.MouseButtonRelease, QtCore.QEvent.MouseButtonDblClick)
                and event.button() == Qt.LeftButton
            )
            or (
                event.type() == QtCore.QEvent.KeyPress
                and event.key() in (Qt.Key_Space, Qt.Key_Select)
            )
        ):
            self._btn.toggle()
            self.setModelData(self._btn, model, index)
            self.commitData.emit(self._btn)
            return True
        return False


class ElogItem:
    def __init__(self, elog, readState=Qt.Unchecked, importantState=Qt.Unchecked):
        self._elog = elog
        self._readState = readState
        self._importantState = importantState

    def filename(self):
        return self._elog.filename

    def category(self):
        return self._elog.category

    def package(self):
        return self._elog.package

    def isoTime(self):
        return time.strftime("%Y-%m-%d %H:%M:%S", self._elog.date)

    def localeTime(self):
        return time.strftime("%x %X", self._elog.date)

    def eclass(self):
        return self._elog.eclass

    def readState(self):
        return self._readState

    def setReadState(self, state):
        self._readState = state

    def isReadState(self):
        return self.readState() == Qt.Checked

    def toggleReadState(self):
        self.setReadState(Qt.Unchecked if self.isReadState() else Qt.Checked)

    def importantState(self):
        return self._importantState

    def setImportantState(self, state):
        self._importantState = state

    def isImportantState(self):
        return self.importantState() == Qt.Checked

    def toggleImportantState(self):
        self.setImportantState(Qt.Unchecked if self.isImportantState() else Qt.Checked)

    def html(self):
        header = "<h1>{category}/{package}</h1>".format(
            category=self.category(), package=self.package()
        )
        text = self._elog.html
        return header + text


class Model(QtCore.QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []  # A list of ElogItem.

    def importantState(self, index):
        return self.itemFromIndex(index).importantState()

    def setImportantState(self, index, state):
        if index.column() != Column.ImportantState:
            return False
        self.itemFromIndex(index).setImportantState(state)
        self.dataChanged.emit(index, index)
        return True

    def toggleImportantState(self, index):
        return self.setImportantState(
            index,
            Qt.Unchecked if self.importantState(index) is Qt.Checked else Qt.Checked,
        )

    def readState(self, index):
        return self.itemFromIndex(index).readState()

    def setReadState(self, index, state):
        if index.column() != Column.ReadState:
            return False
        self.itemFromIndex(index).setReadState(state)
        self.dataChanged.emit(
            self.index(index.row(), 0, index.parent()),
            self.index(index.row(), self.columnCount() - 1, index.parent()),
        )
        return True

    def toggleReadState(self, index):
        return self.setReadState(index, not self.readState(index))

    def itemFromIndex(self, index):
        return self._data[index.row()]

    def item(self, row, _column=0):
        return self._data[row]

    def appendItem(self, item):
        self._data.append(item)

    def rowCount(self, _parent=QtCore.QModelIndex()):
        return len(self._data)

    def columnCount(self, _parent=QtCore.QModelIndex()):
        return len(Column)

    def removeRows(self, row, count, parent=QtCore.QModelIndex()):
        last = min(self.rowCount(), row + count)
        self.beginRemoveRows(parent, row, max(row, last - 1))
        idx = -1
        for idx in range(row, row + count):
            self._data.pop(row)
        self.endRemoveRows()
        return idx > -1

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation != Qt.Horizontal or role != Qt.DisplayRole:
            return super().headerData(section, orientation, role)
        return {
            Column.ImportantState: "!!",
            Column.ReadState: "Read",
            Column.Eclass: "Highest\neclass",
        }.pop(section, Column(section).name)

    def flags(self, index):
        if index.column() in (Column.ImportantState, Column.ReadState):
            return super().flags(index) | Qt.ItemIsEditable
        return super().flags(index)

    def data(self, index, role=Qt.DisplayRole):
        item = self._data[index.row()]
        if role in (Qt.DisplayRole, Qt.EditRole):
            return {
                Column.Category: item.category(),
                Column.Package: item.package(),
                Column.Eclass: item.eclass().name,
                Column.Date: item.localeTime(),
            }.get(index.column(), "")
        if role == Qt.CheckStateRole:
            return {
                Column.ImportantState: item.importantState(),
                Column.ReadState: item.readState(),
            }.get(index.column())
        if role == Role.SortRole:
            key = {
                Column.ImportantState: item.importantState,
                Column.ReadState: item.readState,
                Column.Date: item.isoTime,
                Column.Eclass: lambda: item.eclass().value,
                Column.Category: item.category().lower,
                Column.Package: item.package().lower,
            }.get(index.column(), lambda: self.data(index, Qt.DisplayRole))()
            return "%s%s" % (key, item.isoTime())
        return None

    def setData(self, index, value, role=Qt.EditRole):
        try:
            {
                Column.ImportantState: self.toggleImportantState,
                Column.ReadState: self.toggleReadState,
            }[index.column()](index)
        except KeyError:
            return super().setData(index, value, role)
        else:
            return True


class ElogviewerUi(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        centralWidget = QtWidgets.QWidget(self)
        centralLayout = QtWidgets.QVBoxLayout()
        centralWidget.setLayout(centralLayout)
        self.setCentralWidget(centralWidget)

        self.tableView = QtWidgets.QTableView(centralWidget)
        self.tableView.setSortingEnabled(True)
        self.tableView.setSelectionMode(self.tableView.ExtendedSelection)
        self.tableView.setSelectionBehavior(self.tableView.SelectRows)
        horizontalHeader = self.tableView.horizontalHeader()
        horizontalHeader.setSectionsClickable(True)
        horizontalHeader.setSectionResizeMode(horizontalHeader.ResizeToContents)
        horizontalHeader.setStretchLastSection(True)
        self.tableView.verticalHeader().hide()
        centralLayout.addWidget(self.tableView)

        self.textEdit = QtWidgets.QTextBrowser(centralWidget)
        self.textEdit.setOpenExternalLinks(True)
        self.textEdit.setText("""No elog selected.""")
        centralLayout.addWidget(self.textEdit)

        self.toolBar = QtWidgets.QToolBar(self)
        self.addToolBar(self.toolBar)

        self.statusLabel = QtWidgets.QLabel(self.statusBar())
        self.statusBar().addWidget(self.statusLabel)
        self.unreadLabel = QtWidgets.QLabel(self.statusBar())
        self.statusBar().addWidget(self.unreadLabel)


class Elogviewer(ElogviewerUi):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.settings = QtCore.QSettings("elogviewer", "elogviewer")
        if not self.settings.contains("readFlag"):
            self.settings.setValue("readFlag", set())
        if not self.settings.contains("importantFlag"):
            self.settings.setValue("importantFlag", set())
        if self.settings.contains("windowWidth") and self.settings.contains(
            "windowHeight"
        ):
            self.resize(
                int(self.settings.value("windowWidth")),
                int(self.settings.value("windowHeight")),
            )
        else:
            screenSize = QtWidgets.QApplication.desktop().screenGeometry()
            self.resize(screenSize.width() // 2, screenSize.height() // 2)

        self.model = Model(self.tableView)
        self.model.dataChanged.connect(self.saveSettings)
        self.proxyModel = QtCore.QSortFilterProxyModel(self.tableView)
        self.proxyModel.setFilterKeyColumn(Column.Package)
        self.proxyModel.setSortRole(Role.SortRole)
        self.proxyModel.setSourceModel(self.model)
        self.tableView.setModel(self.proxyModel)

        horizontalHeader = self.tableView.horizontalHeader()
        horizontalHeader.sortIndicatorChanged.connect(self.proxyModel.sort)

        for column, delegate in (
            (Column.ImportantState, ButtonDelegate(Star(), self.tableView)),
            (Column.ReadState, ButtonDelegate(Bullet(), self.tableView)),
            (Column.Eclass, SeverityColorDelegate(self.tableView)),
        ):
            self.tableView.setItemDelegateForColumn(column, delegate)
        self.tableView.setItemDelegate(ReadFontStyleDelegate(self.tableView))

        self.textEditMapper = QtWidgets.QDataWidgetMapper(self.tableView)
        self.textEditMapper.setSubmitPolicy(self.textEditMapper.AutoSubmit)
        self.textEditMapper.setItemDelegate(TextToHtmlDelegate(self.textEditMapper))
        self.textEditMapper.setModel(self.model)
        self.textEditMapper.addMapping(self.textEdit, 0)
        self.tableView.selectionModel().currentRowChanged.connect(
            lambda curr, prev: self.textEditMapper.setCurrentModelIndex(
                _sourceIndex(curr)
            )
        )

        iconFromTheme = QtGui.QIcon.fromTheme
        self.refreshAction = QtWidgets.QAction(
            iconFromTheme("view-refresh"),
            "Refresh",
            self.toolBar,
            shortcut=QtGui.QKeySequence.Refresh,
            triggered=self.populate,
        )
        self.markReadAction = QtWidgets.QAction(
            iconFromTheme("mail-mark-read"),
            "Mark read",
            self.toolBar,
            triggered=partial(self.setSelectedReadState, Qt.Checked),
        )
        self.markUnreadAction = QtWidgets.QAction(
            iconFromTheme("mail-mark-unread"),
            "Mark unread",
            self.toolBar,
            triggered=partial(self.setSelectedReadState, Qt.Unchecked),
        )
        self.toggleImportantAction = QtWidgets.QAction(
            iconFromTheme("mail-mark-important"),
            "Important",
            self.toolBar,
            triggered=self.toggleSelectedImportantState,
        )
        self.deleteAction = QtWidgets.QAction(
            iconFromTheme("edit-delete"),
            "Delete",
            self.toolBar,
            shortcut=QtGui.QKeySequence.Delete,
            triggered=self.deleteSelected,
        )
        self.aboutAction = QtWidgets.QAction(
            iconFromTheme("help-about"),
            "About",
            self.toolBar,
            shortcut=QtGui.QKeySequence.HelpContents,
            triggered=partial(
                QtWidgets.QMessageBox.about,
                self,
                "About (k)elogviewer",
                "<h1>(k)elogviewer %s</h1>"
                "<center><small>"
                "(k)elogviewer, copyright (c) 2007-2016 Mathias Laurin<br>"
                "kelogviewer, copyright (c) 2007 Jeremy Wickersheimer<br>"
                "GNU General Public License (GPL) version 2</small><br>"
                "<a href=http://sourceforge.net/projects/elogviewer>"
                "http://sourceforge.net/projects/elogviewer</a>"
                "</center>"
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
        self.exitAction = QtWidgets.QAction(
            iconFromTheme("application-exit"),
            "Quit",
            self.toolBar,
            shortcut=QtGui.QKeySequence.Quit,
            triggered=self.close,
        )
        self.toolBar.addAction(self.refreshAction)
        self.toolBar.addAction(self.markReadAction)
        self.toolBar.addAction(self.markUnreadAction)
        self.toolBar.addAction(self.toggleImportantAction)
        self.toolBar.addAction(self.deleteAction)
        self.toolBar.addAction(self.aboutAction)
        self.toolBar.addAction(self.exitAction)

        def fromToolBar(name):
            action = getattr(self, "%sAction" % name)
            return self.toolBar.widgetForAction(action)

        self.refreshButton = fromToolBar("refresh")
        self.markReadButton = fromToolBar("markRead")
        self.markUnreadButton = fromToolBar("markUnread")
        self.toggleImportantButton = fromToolBar("toggleImportant")
        self.deleteButton = fromToolBar("delete")
        self.aboutButton = fromToolBar("about")

        self.tableView.selectionModel().currentRowChanged.connect(
            self.onCurrentRowChanged
        )

        self.searchLineEdit = QtWidgets.QLineEdit(self.toolBar)
        self.searchLineEdit.setPlaceholderText("search")
        self.searchLineEdit.textEdited.connect(self.proxyModel.setFilterRegExp)
        self.toolBar.addWidget(self.searchLineEdit)

        QtCore.QTimer.singleShot(100, self.populate)
        if self.settings.contains("sortColumn") and self.settings.contains("sortOrder"):
            self.tableView.sortByColumn(
                int(self.settings.value("sortColumn")),
                int(self.settings.value("sortOrder")),
            )
        else:
            self.tableView.sortByColumn(Column.Date, Qt.DescendingOrder)
        self.tableView.selectRow(0)

    def saveSettings(self):
        readFlag = set()
        importantFlag = set()
        for row in range(self.model.rowCount()):
            item = self.model.item(row, Column.ReadState)
            if item.readState() == Qt.Checked:
                readFlag.add(item.filename())
            if item.importantState() == Qt.Checked:
                importantFlag.add(item.filename())
        self.settings.setValue("readFlag", readFlag)
        self.settings.setValue("importantFlag", importantFlag)
        self.settings.setValue(
            "sortColumn", self.tableView.horizontalHeader().sortIndicatorSection()
        )
        self.settings.setValue(
            "sortOrder", self.tableView.horizontalHeader().sortIndicatorOrder()
        )
        self.settings.setValue("windowWidth", self.width())
        self.settings.setValue("windowHeight", self.height())

    def onCurrentRowChanged(self, current, previous):
        if previous.row() != -1:
            index = self.model.index(
                _sourceIndex(current).row(), Column.ReadState, current.parent()
            )
            self.model.setReadState(index, Qt.Checked)
        self.updateStatus()
        self.updateUnreadCount()

    def updateStatus(self):
        text = "%i of %i elogs" % (self.currentRow() + 1, self.elogCount())
        self.statusLabel.setText(text)

    def updateUnreadCount(self):
        text = "%i unread" % self.unreadCount()
        self.unreadLabel.setText(text)
        self.setWindowTitle("Elogviewer (%s)" % text)

    def currentRow(self):
        return self.tableView.selectionModel().currentIndex().row()

    def rowCount(self):
        return self.proxyModel.rowCount()

    def elogCount(self):
        return self.model.rowCount()

    def readCount(self):
        count = 0
        for row in range(self.model.rowCount()):
            if self.model.item(row).isReadState():
                count += 1
        return count

    def unreadCount(self):
        return self.elogCount() - self.readCount()

    def importantCount(self):
        count = 0
        for row in range(self.model.rowCount()):
            if self.model.item(row).isImportantState():
                count += 1
        return count

    def setSelectedReadState(self, state):
        for index in self.tableView.selectionModel().selectedIndexes():
            self.model.setReadState(_sourceIndex(index), state)
        self.updateUnreadCount()

    def toggleSelectedImportantState(self):
        state = None
        for index in self.tableView.selectionModel().selectedRows(
            Column.ImportantState
        ):
            sourceIndex = _sourceIndex(index)
            if state is None:
                state = (
                    Qt.Unchecked
                    if self.model.importantState(sourceIndex) is Qt.Checked
                    else Qt.Checked
                )
            self.model.setImportantState(sourceIndex, state)

    def deleteSelected(self):
        selection = [
            self.proxyModel.mapToSource(idx)
            for idx in self.tableView.selectionModel().selectedRows()
        ]
        selection.sort(key=lambda idx: idx.row())
        # Avoid call to onCurrentRowChanged() by clearing
        # selection with reset().
        currentRow = self.currentRow()
        self.tableView.selectionModel().reset()

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

    def populate(self):
        currentRow = self.currentRow()
        self.tableView.selectionModel().reset()
        self.model.removeRows(0, self.model.rowCount())
        self.model.beginResetModel()
        for filename in itertools.chain(
            glob.iglob(os.path.join(self.config.elogpath, "*:*:*.log*")),
            glob.iglob(os.path.join(self.config.elogpath, "*", "*:*.log*")),
        ):
            item = ElogItem(Elog.fromFilename(filename))
            item.setReadState(
                Qt.Checked
                if filename in self.settings.value("readFlag")
                else Qt.Unchecked
            )
            item.setImportantState(
                Qt.Checked
                if filename in self.settings.value("importantFlag")
                else Qt.Unchecked
            )
            self.model.appendItem(item)
        self.model.endResetModel()
        self.tableView.selectRow(min(currentRow, self.rowCount() - 1))


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-p", "--elogpath", help="path to the elog directory", default=""
    )
    parser.add_argument(
        "--log",
        choices="DEBUG INFO WARNING ERROR".split(),
        default="WARNING",
        help="set logging level",
    )

    config = parser.parse_args()

    logging.basicConfig()
    _LOGGER.setLevel(getattr(logging, config.log))

    _LOGGER.debug("running on python %s", sys.version)
    if portage and not config.elogpath:
        # pylint: disable=no-member
        logdir = portage.settings["PORT_LOGDIR"]
        if not logdir:
            logdir = os.path.join(
                portage.settings["EPREFIX"] if portage.settings["EPREFIX"] else os.sep,
                "var",
                "log",
                "portage",
            )
        config.elogpath = os.path.join(logdir, "elog")

    _LOGGER.debug("elogpath is set to %r", config.elogpath)

    app = QtWidgets.QApplication(argv)
    app.setWindowIcon(QtGui.QIcon.fromTheme("applications-system"))

    elogviewer = Elogviewer(config)
    elogviewer.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main(sys.argv)
