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

from __future__ import annotations

import abc
import argparse
import bz2
import enum
import glob
import gzip
import io
import itertools
import logging
import os
import re
import sys
import time
import weakref
from contextlib import AbstractContextManager, closing, suppress
from dataclasses import dataclass
from functools import partial
from math import cos, sin
from typing import IO, Protocol

from PyQt6 import QtCore, QtGui, QtWidgets

try:
    import portage  # type: ignore[import-not-found]
except ImportError:
    portage = None  # type: ignore

try:
    from importlib.metadata import version as _version

    __version__ = _version("elogviewer")
except Exception:
    __version__ = "unknown"


Qt = QtCore.Qt

_LOGGER = logging.getLogger("elogviewer")


class Role(enum.IntEnum):
    SortRole = Qt.ItemDataRole.UserRole + 1


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

    def color(self) -> QtGui.QColor:
        return {
            "Error": QtGui.QColor(QtGui.QColorConstants.Red),
            "Warning": QtGui.QColor(229, 103, 23),
            "Log": QtGui.QColor(QtGui.QColorConstants.DarkGreen),
            "Info": QtGui.QColor(QtGui.QColorConstants.DarkGreen),
            "QA": QtGui.QColor(QtGui.QColorConstants.DarkGreen),
        }[self.name]

    def htmlColor(self) -> str:
        return self.color().name()


@dataclass(frozen=True)
class Elog:
    filename: str
    category: str
    package: str
    date: time.struct_time
    eclass: EClass

    HeaderPattern = re.compile(
        r"({}):\s+(\S+)".format("|".join(_.value for _ in EClass))
    )
    AnsiColorPattern = re.compile(r"\x1b\[[0-9;]+m")
    LinkPattern = re.compile(r"((https?|ftp)://\S+)", re.IGNORECASE)
    BugPattern = re.compile(r"([bB]ug)\s+#([0-9]+)", re.IGNORECASE)
    PackagePattern = re.compile(
        r"([a-z0-9]+-[a-z0-9]+/[a-z0-9]+)-([0-9.]+)", re.IGNORECASE
    )

    @staticmethod
    def __file(filename: str) -> AbstractContextManager[IO[str]]:
        # Static so that it may be called *before* instantiation.
        _, ext = os.path.splitext(filename)
        try:
            return {".gz": gzip.open, ".bz2": bz2.open, ".log": open}[ext](
                filename, "rt"
            )
        except KeyError:
            _LOGGER.error("%s: unsupported format", filename)
            return closing(
                io.StringIO(
                    """
                    <!-- set eclass: ERROR: -->
                    <h3>Unsupported format</h3>
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
                    <h3>File not found</h3>
                    The selected elog could does not exist on the filesystem.
                    """
                )
            )
        except OSError:
            _LOGGER.error("%s: could not open file", filename)
            return closing(
                io.StringIO(
                    """
                    <!-- set eclass: ERROR: -->
                    <h3>File does not open</h3>
                    The selected elog could not be opened.
                    """
                )
            )

    @property
    def file(self) -> AbstractContextManager[IO[str]]:
        return self.__file(self.filename)

    @classmethod
    def fromFilename(cls, filename: str | os.PathLike[str]) -> Elog:
        filename = os.fspath(filename)
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
    def getClass(cls, elogBody: str) -> EClass:
        # Get the highest elog class. Adapted from Luca Marturana's elogv.
        eClasses = frozenset(_[0] for _ in cls.HeaderPattern.findall(elogBody))
        for eClass in EClass:
            if eClass.value in eClasses:
                return eClass
        _LOGGER.error("elog has no identifiable eclass")
        return EClass.Log

    @property
    def contents(self) -> str:
        with self.file as file:
            return file.read()

    @property
    def html(self) -> str:
        parsed = []
        with ParserFSM(parsed) as parser, self.file as file:
            for line in file:
                parser.parse(line)
        return os.linesep.join(_ for _ in parsed if _ is not None)


def _sourceIndex(index: QtCore.QModelIndex) -> QtCore.QModelIndex:
    model = index.model()
    with suppress(AttributeError):
        index = model.mapToSource(index)  # type: ignore  # proxy
    return index


def _itemFromIndex(index: QtCore.QModelIndex) -> ElogItem:
    assert index.isValid()
    model = _sourceIndex(index).model()
    assert isinstance(model, Model)
    return model.itemFromIndex(index)


class TextToHtmlDelegate(QtWidgets.QItemDelegate):
    def __repr__(self) -> str:
        return f"elogviewer.{self.__class__.__name__}({self.parent()!r})"

    def setEditorData(
        self, editor: QtWidgets.QWidget | None, index: QtCore.QModelIndex
    ) -> None:
        if not index.isValid() or not isinstance(editor, QtWidgets.QTextEdit):
            return
        model = index.model()
        assert isinstance(model, Model)
        editor.setHtml(model.itemFromIndex(index).html())


class AbstractState(abc.ABC):
    def __init__(self, context: ParserFSM) -> None:
        self.context = weakref.proxy(context)

    def __str__(self) -> str:
        return type(self).__name__

    @abc.abstractmethod
    def enter(self) -> str | None:
        """Entry action."""

    @abc.abstractmethod
    def exit(self) -> str | None:
        """Exit action."""

    @abc.abstractmethod
    def parse(self, line: str) -> str | None:
        """Do action."""


class NoopState(AbstractState):
    def enter(self) -> None:
        pass

    def exit(self) -> None:
        pass

    def parse(self, line: str) -> str:
        return line


class HeaderState(AbstractState):
    def enter(self) -> str:
        return "<h3>"

    def exit(self) -> str:
        return "</h3>"

    def parse(self, line: str) -> str:
        try:
            eclass, stage = line.split(":")
        except ValueError:
            # Not a header, e.g., "Too many values to unpack (expected 2)"
            return ""

        self.context.eclass = {
            "ERROR": EClass.Error,
            "WARN": EClass.Warning,
            "LOG": EClass.Log,
            "INFO": EClass.Info,
            "QA": EClass.QA,
        }[eclass]
        return f"{self.context.eclass.name}: {stage}"


class BodyState(AbstractState):
    _HREF = r'<a href="{url}">{text}</a>'
    _LINK_REPL = _HREF.format(url=r"\1", text=r"\1")
    _BUG_REPL = _HREF.format(url=r"https://bugs.gentoo.org/\2", text=r"\1 #\2")
    _PKG_REPL = _HREF.format(
        url=r"http://packages.gentoo.org/packages/\1", text=r"\1-\2"
    )

    @classmethod
    def _parse_link(cls, line: str) -> str:
        return Elog.LinkPattern.sub(cls._LINK_REPL, line)

    @classmethod
    def _parse_bug(cls, line: str) -> str:
        return Elog.BugPattern.sub(cls._BUG_REPL, line)

    @classmethod
    def _parse_pkg(cls, line: str) -> str:
        return Elog.PackagePattern.sub(cls._PKG_REPL, line)

    @classmethod
    def _parse_ansi_colors(cls, line: str) -> str:
        return Elog.AnsiColorPattern.sub("", line)

    def enter(self) -> str:
        return f'<p style="color: {self.context.eclass.htmlColor()}">'

    def exit(self) -> str:
        return "</p>"

    def parse(self, line: str) -> str:
        line = self._parse_ansi_colors(line)
        line = self._parse_link(line)
        line = self._parse_bug(line)
        line = self._parse_pkg(line)
        return f"{line} <br />"


class ParserFSM:
    def __init__(self, results: list[str | None]) -> None:
        self.eclass = EClass.Log
        self._results = results
        self._noopState = NoopState(self)
        self._headerState = HeaderState(self)
        self._bodyState = BodyState(self)

    @property
    def state(self) -> AbstractState:
        return self.__dict__.get("state", self._noopState)

    @state.setter
    def state(self, state: AbstractState) -> None:
        if state is not self.state:
            self._results.append(self.state.exit())
            self.__dict__["state"] = state
            self._results.append(self.state.enter())

    def __str__(self) -> str:
        return f"{type(self).__name__}: {self.state}"

    def __enter__(self) -> ParserFSM:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        if any(exc_info):
            return False
        self.state = self._noopState
        return True

    def _stateFor(self, line: str) -> AbstractState:
        if Elog.HeaderPattern.match(line) and self._headerState.parse(line):
            return self._headerState
        return self._bodyState

    def parse(self, line: str) -> None:
        if not line.strip():
            return
        self.state = self._stateFor(line)
        self._results.append(self.state.parse(line))


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
            color = EClass[option.text].color()
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
            _itemFromIndex(index).readState() == Qt.CheckState.Unchecked
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
                    0.5 + 0.5 * cos(0.8 * i * 3.14), 0.5 + 0.5 * sin(0.8 * i * 3.14)
                )
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
        return "elogviewer.{}(button={!r}, parent={!r})".format(
            self.__class__.__name__,
            self._btn,
            self.parent(),
        )

    def sizeHint(
        self, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex
    ) -> QtCore.QSize:
        return super().sizeHint(option, index)

    def createEditor(
        self,
        parent: QtWidgets.QWidget | None,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> QtWidgets.QWidget | None:  # noqa: ARG002
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
            index.data(role=Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
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
            or (
                event.type() == QtCore.QEvent.Type.KeyPress
                and isinstance(event, QtGui.QKeyEvent)
                and event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Select)
            )
        ):
            self._btn.toggle()
            self.setModelData(self._btn, model, index)
            self.commitData.emit(self._btn)
            return True
        return False


class ElogItem:
    def __init__(
        self,
        elog: Elog,
        readState: Qt.CheckState = Qt.CheckState.Unchecked,
        importantState: Qt.CheckState = Qt.CheckState.Unchecked,
    ) -> None:
        self._elog = elog
        self._readState = readState
        self._importantState = importantState

    def filename(self) -> str:
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

    def readState(self) -> Qt.CheckState:
        return self._readState

    def setReadState(self, state: Qt.CheckState) -> None:
        self._readState = state

    def isReadState(self) -> bool:
        return self.readState() == Qt.CheckState.Checked

    def toggleReadState(self) -> None:
        self.setReadState(
            Qt.CheckState.Unchecked if self.isReadState() else Qt.CheckState.Checked
        )

    def importantState(self) -> Qt.CheckState:
        return self._importantState

    def setImportantState(self, state: Qt.CheckState) -> None:
        self._importantState = state

    def isImportantState(self) -> bool:
        return self.importantState() == Qt.CheckState.Checked

    def toggleImportantState(self) -> None:
        self.setImportantState(
            Qt.CheckState.Unchecked
            if self.isImportantState()
            else Qt.CheckState.Checked
        )

    def html(self) -> str:
        header = "<h2>{category}/{package}</h2>".format(
            category=self.category(), package=self.package()
        )
        text = self._elog.html
        return header + text


class Model(QtCore.QAbstractTableModel):
    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._data: list[ElogItem] = []  # A list of ElogItem.

    def importantState(self, index: QtCore.QModelIndex) -> Qt.CheckState:
        return self.itemFromIndex(index).importantState()

    def setImportantState(
        self, index: QtCore.QModelIndex, state: Qt.CheckState
    ) -> bool:
        if index.column() != Column.ImportantState:
            return False
        self.itemFromIndex(index).setImportantState(state)
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
        return self.itemFromIndex(index).readState()

    def setReadState(self, index: QtCore.QModelIndex, state: Qt.CheckState) -> bool:
        if index.column() != Column.ReadState:
            return False
        self.itemFromIndex(index).setReadState(state)
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

    def itemFromIndex(self, index: QtCore.QModelIndex) -> ElogItem:
        return self._data[index.row()]

    def item(self, row: int, _column: int = 0) -> ElogItem:
        return self._data[row]

    def appendItem(self, item: ElogItem) -> None:
        self._data.append(item)

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(self._data)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(Column)

    def removeRows(
        self, row: int, count: int, parent: QtCore.QModelIndex = QtCore.QModelIndex()
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

    def data(
        self, index: QtCore.QModelIndex, role: int = Qt.ItemDataRole.DisplayRole
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
                index.column(), lambda: self.data(index, Qt.ItemDataRole.DisplayRole)
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
            horizontalHeader.ResizeMode.ResizeToContents
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
            "windowHeight"
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
                _sourceIndex(curr)
            )
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
            self.proxyModel.setFilterRegularExpression
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
        self, current: QtCore.QModelIndex, previous: QtCore.QModelIndex
    ) -> None:
        if previous.row() != -1:
            index = self.model.index(
                _sourceIndex(current).row(), Column.ReadState, current.parent()
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
            item = ElogItem(Elog.fromFilename(filename))
            item.setReadState(
                Qt.CheckState.Checked
                if filename in self.settings.value("readFlag")
                else Qt.CheckState.Unchecked
            )
            item.setImportantState(
                Qt.CheckState.Checked
                if filename in self.settings.value("importantFlag")
                else Qt.CheckState.Unchecked
            )
            self.model.appendItem(item)
        self.model.endResetModel()
        self.tableView.selectRow(min(currentRow, self.rowCount() - 1))


def main() -> None:
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
        logdir = portage.settings["PORT_LOGDIR"]  # type: ignore
        if not logdir:
            logdir = os.path.join(
                portage.settings["EPREFIX"] if portage.settings["EPREFIX"] else os.sep,  # type: ignore
                "var",
                "log",
                "portage",
            )
        config.elogpath = os.path.join(logdir, "elog")

    _LOGGER.debug("elogpath is set to %r", config.elogpath)

    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(QtGui.QIcon.fromTheme("applications-system"))

    elogviewer = Elogviewer(config)
    elogviewer.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
