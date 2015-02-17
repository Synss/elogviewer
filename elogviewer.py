#!/usr/bin/env python
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

import sys
import os
import logging
logger = logging.getLogger(__name__)
import argparse
import locale
import time
import re
from math import cos, sin
from glob import glob
from functools import partial
from contextlib import closing

from enum import Enum
from io import BytesIO

import gzip
import bz2
try:
    import liblzma as lzma
except ImportError:
    lzma = None

try:
    import sip as _sip
except ImportError:
    from PySide import QtGui, QtCore
    QtCore.QSortFilterProxyModel = QtGui.QSortFilterProxyModel
    QtWidgets = QtGui
else:
    try:
        from PyQt5 import QtGui, QtWidgets, QtCore
    except ImportError:
        for _type in "QDate QDateTime QString QVariant".split():
            _sip.setapi(_type, 2)
        from PyQt4 import QtGui, QtCore
        QtCore.QSortFilterProxyModel = QtGui.QSortFilterProxyModel
        QtWidgets = QtGui

Qt = QtCore.Qt

try:
    import portage
except ImportError:
    portage = None


__version__ = "2.4"


def _(bytes):
    """This helper changes `bytes` to `str` on python3 and does nothing
    under python2.

    """
    return bytes.decode(locale.getpreferredencoding())


class Role(Enum):

    SortRole = Qt.UserRole + 1


class Column(Enum):

    ImportantState = 0
    Category = 1
    Package = 2
    ReadState = 3
    Eclass = 4
    Date = 5


class Color(Enum):

    eerror = QtGui.QColor(Qt.red)
    ewarn = QtGui.QColor(229, 103, 23)
    einfo = QtGui.QColor(Qt.darkGreen)
    elog = QtGui.QColor(Qt.black)

    def toHtml(self):
        color = self.value
        return "#%02X%02X%02X" % (color.red(), color.green(), color.blue())


def _sourceIndex(index):
    model = index.model()
    try:
        index = model.mapToSource(index)  # proxy
    except AttributeError:
        pass
    return index


def _itemFromIndex(index):
    index = _sourceIndex(index)
    return index.model().itemFromIndex(index)


class Elog(object):

    _readFlag = set()
    _importantFlag = set()

    def __init__(self, filename):
        self.filename = filename
        basename = os.path.basename(filename)
        try:
            self.category, self.package, rest = basename.split(":")
        except ValueError:
            self.category = os.path.dirname(filename).split(os.sep)[-1]
            self.package, rest = basename.split(":")
        date = rest.split(".")[0]
        self.date = time.strptime(date, "%Y%m%d-%H%M%S")

        # Get the highest elog class. Adapted from Luca Marturana's elogv.
        with self.file as elogfile:
            eClasses = re.findall("LOG:|INFO:|WARN:|ERROR:",
                                  _(elogfile.read()))
            if "ERROR:" in eClasses:
                self.eclass = "eerror"
            elif "WARN:" in eClasses:
                self.eclass = "ewarn"
            elif "LOG:" in eClasses:
                self.eclass = "elog"
            else:
                self.eclass = "einfo"

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, self.filename)

    def delete(self):
        os.remove(self.filename)
        Elog._readFlag.remove(self.filename)

    @property
    def file(self):
        root, ext = os.path.splitext(self.filename)
        try:
            return {".gz": gzip.open,
                    ".bz2": bz2.BZ2File,
                    ".log": open}[ext](self.filename, "rb")
        except KeyError:
            logger.error("%s: unsupported format" % self.filename)
            return closing(BytesIO(
                b"""
                <!-- set eclass: ERROR: -->
                <h2>Unsupported format</h2>
                The selected elog is in an unsupported format.
                """
            ))
        except IOError:
            logger.error("%s: could not open file" % self.filename)
            return closing(BytesIO(
                b"""
                <!-- set eclass: ERROR: -->
                <h2>File does not open</h2>
                The selected elog could not be opened.
                """
            ))

    @property
    def importantFlag(self):
        return self.filename in Elog._importantFlag

    @importantFlag.setter
    def importantFlag(self, flag):
        if flag:
            Elog._importantFlag.add(self.filename)
        else:
            try:
                Elog._importantFlag.remove(self.filename)
            except KeyError:
                pass

    @property
    def isoTime(self):
        return time.strftime("%Y-%m-%d %H:%M:%S", self.date)

    @property
    def localeTime(self):
        return time.strftime("%x %X", self.date)

    @property
    def readFlag(self):
        return self.filename in Elog._readFlag

    @readFlag.setter
    def readFlag(self, flag):
        if flag:
            Elog._readFlag.add(self.filename)
        else:
            try:
                Elog._readFlag.remove(self.filename)
            except KeyError:
                pass


class TextToHtmlDelegate(QtWidgets.QItemDelegate):

    def __init__(self, parent=None):
        super(TextToHtmlDelegate, self).__init__(parent)

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, self.parent())

    def setEditorData(self, editor, index):
        if not index.isValid() or not isinstance(editor, QtWidgets.QTextEdit):
            return
        model = index.model()
        elog = model.itemFromIndex(index).elog()
        editor.setHtml(TextToHtmlDelegate.toHtml(elog))

    @staticmethod
    def toHtml(elog):
        join = os.linesep.join
        text = ""
        with elog.file as elogfile:
            for line in elogfile:
                line = _(line.strip())
                # Color eclasses
                prefix = '<p style="color: {color}">'
                if line.startswith("ERROR:"):
                    prefix = prefix.format(color=Color["eerror"].toHtml())
                elif line.startswith("WARN:"):
                    prefix = prefix.format(color=Color["ewarn"].toHtml())
                elif line.startswith("INFO:"):
                    prefix = prefix.format(color=Color["einfo"].toHtml())
                elif line.startswith("LOG:") or line.startswith("QA:"):
                    prefix = prefix.format(color=Color["elog"].toHtml())
                else:
                    prefix = ""
                if text and prefix:
                    text = join((text, "</p>"))
                # EOL
                text = join((text, "".join((prefix, line, " <br />"))))
        text = join((text, "</p>"))
        # Strip ANSI colors
        text = re.sub("\x1b\[[0-9;]+m", "", text)
        # Hyperlink
        text = re.sub("((https?|ftp)://\S+)", r'<a href="\1">\1</a>', text)
        # Hyperlink bugs
        text = re.sub(
            "bug\s+#([0-9]+)",
            r'<a href="https://bugs.gentoo.org/\1">bug #\1</a>',
            text)
        # Hyperlink packages
        text = re.sub(
            "\s([a-z1]+[-][a-z0-9]+/[a-z0-9-]+)\s",
            r'<a href="http://packages.gentoo.org/package/\1"> \1 </a>', text)
        return text


class SeverityColorDelegate(QtWidgets.QStyledItemDelegate):

    def __init__(self, parent=None):
        super(SeverityColorDelegate, self).__init__(parent)

    def paint(self, painter, option, index):
        if not index.isValid():
            return
        self.initStyleOption(option, index)
        try:
            color = Color[option.text].value
        except KeyError:
            pass
        else:
            option.palette.setColor(QtGui.QPalette.Text, color)
        super(SeverityColorDelegate, self).paint(painter, option, index)


class ReadFontStyleDelegate(QtWidgets.QStyledItemDelegate):

    def __init__(self, parent=None):
        super(ReadFontStyleDelegate, self).__init__(parent)

    def paint(self, painter, option, index):
        if not index.isValid():
            return
        self.initStyleOption(option, index)
        option.font.setBold(not _itemFromIndex(index).isReadState())
        super(ReadFontStyleDelegate, self).paint(painter, option, index)


class Bullet(QtWidgets.QAbstractButton):

    _scaleFactor = 20

    def __init__(self, parent=None):
        super(Bullet, self).__init__(parent)
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
        super(Star, self).__init__(parent)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setCheckable(True)
        self._starPolygon = QtGui.QPolygonF([QtCore.QPointF(1.0, 0.5)])
        for i in range(5):
            self._starPolygon << QtCore.QPointF(
                0.5 + 0.5 * cos(0.8 * i * 3.14),
                0.5 + 0.5 * sin(0.8 * i * 3.14))

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
        super(ButtonDelegate, self).__init__(parent)
        self._btn = QtWidgets.QPushButton() if button is None else button
        self._btn.setParent(parent)
        self._btn.hide()

    def __repr__(self):
        return "%s(button=%r, parent=%r)" % (
            self.__class__.__name__, self._btn, self.parent())

    def sizeHint(self, option, index):
        return super(ButtonDelegate, self).sizeHint(option, index)

    def createEditor(self, parent, option, index):
        return None

    def setModelData(self, editor, model, index):
        model.setData(index, editor.isChecked(), role=Qt.CheckStateRole)

    def paint(self, painter, option, index):
        self._btn.setChecked(index.data(role=Qt.CheckStateRole))
        self._btn.setGeometry(option.rect)
        if option.state & QtWidgets.QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        try:
            # PyQt5
            pixmap = self._btn.grab()
        except AttributeError:
            # PyQt4
            pixmap = QtGui.QPixmap.grabWidget(self._btn)
        painter.drawPixmap(option.rect.x(), option.rect.y(), pixmap)

    def editorEvent(self, event, model, option, index):
        if (int(index.flags()) & Qt.ItemIsEditable and
            (event.type() in (QtCore.QEvent.MouseButtonRelease,
                              QtCore.QEvent.MouseButtonDblClick) and
             event.button() == Qt.LeftButton) or
            (event.type() == QtCore.QEvent.KeyPress and
             event.key() in (Qt.Key_Space, Qt.Key_Select))):
                self._btn.toggle()
                self.setModelData(self._btn, model, index)
                self.commitData.emit(self._btn)
                return True
        return False


class ElogItem(QtGui.QStandardItem):

    def __init__(self, elog=None):
        super(ElogItem, self).__init__()
        self.__elog = elog

    def type(self):
        return self.UserType + 1

    def clone(self):
        return self.__class__()

    def elog(self):
        return self.__elog

    def setReadState(self, state):
        self.__elog.readFlag = state is Qt.Checked
        self.emitDataChanged()

    def readState(self):
        return Qt.Checked if self.__elog.readFlag else Qt.Unchecked

    def isReadState(self):
        return self.__elog.readFlag is True

    def setImportantState(self, state):
        self.__elog.importantFlag = state is Qt.Checked
        self.emitDataChanged()

    def importantState(self):
        return Qt.Checked if self.__elog.importantFlag else Qt.Unchecked

    def isImportantState(self):
        return self.__elog.importantFlag is True

    def toggleImportantState(self):
        self.setImportantState(Qt.Unchecked if self.isImportantState() else
                               Qt.Checked)

    def data(self, role=Qt.UserRole + 1):
        if not self.__elog:
            return super(ElogItem, self).data(role)
        if role in (Qt.DisplayRole, Qt.EditRole):
            return {
                Column.Category.value: self.__elog.category,
                Column.Package.value: self.__elog.package,
                Column.Eclass.value: self.__elog.eclass,
                Column.Date.value: self.__elog.localeTime,
            }.get(self.column(), "")
        elif role == Qt.CheckStateRole:
            return {
                Column.ImportantState.value: self.importantState,
                Column.ReadState.value: self.readState,
            }.get(self.column(), lambda: None)()
        elif role == Role.SortRole.value:
            if self.column() in (
                    Column.ImportantState.value,
                    Column.ReadState.value):
                return self.data(Qt.CheckStateRole)
            elif self.column() is Column.Date.value:
                return self.__elog.isoTime
            elif self.column() is Column.Eclass.value:
                return {"eerror": 5,
                        "ewarn": 4,
                        "einfo": 3,
                        "elog": 2}.get(self.__elog.eclass, 0)
            else:
                return self.data(Qt.DisplayRole)
        else:
            return super(ElogItem, self).data(role)


def populate(model, path):
    for filename in (glob(os.path.join(path, "*:*:*.log*")) +
                     glob(os.path.join(path, "*", "*:*.log*"))):
        elog = Elog(filename)
        row = []
        for nCol in range(model.columnCount()):
            item = ElogItem(elog)
            item.setEditable(nCol is Column.ImportantState.value)
            row.append(item)
        model.appendRow(row)


class ElogviewerUi(QtWidgets.QMainWindow):

    def __init__(self):
        super(ElogviewerUi, self).__init__()
        centralWidget = QtWidgets.QWidget(self)
        centralLayout = QtWidgets.QVBoxLayout()
        centralWidget.setLayout(centralLayout)
        self.setCentralWidget(centralWidget)

        self.tableView = QtWidgets.QTableView(centralWidget)
        self.tableView.setSelectionMode(self.tableView.ExtendedSelection)
        self.tableView.setSelectionBehavior(self.tableView.SelectRows)
        horizontalHeader = self.tableView.horizontalHeader()
        try:
            # PyQt5
            horizontalHeader.setSectionsClickable(True)
            horizontalHeader.setSectionResizeMode(
                horizontalHeader.ResizeToContents)
        except AttributeError:
            # PyQt4
            horizontalHeader.setClickable(True)
            horizontalHeader.setResizeMode(horizontalHeader.ResizeToContents)
        horizontalHeader.setStretchLastSection(True)
        self.tableView.verticalHeader().hide()
        centralLayout.addWidget(self.tableView)

        self.textEdit = QtWidgets.QTextBrowser(centralWidget)
        self.textEdit.setOpenExternalLinks(True)
        self.textEdit.setText("""No elogs!""")
        centralLayout.addWidget(self.textEdit)

        self.toolBar = QtWidgets.QToolBar(self)
        self.addToolBar(self.toolBar)

        self.statusLabel = QtWidgets.QLabel(self.statusBar())
        self.statusBar().addWidget(self.statusLabel)
        self.unreadLabel = QtWidgets.QLabel(self.statusBar())
        self.statusBar().addWidget(self.unreadLabel)


class Elogviewer(ElogviewerUi):

    def __init__(self, config):
        super(Elogviewer, self).__init__()
        self.config = config
        self.settings = QtCore.QSettings("Mathias Laurin", "elogviewer")
        try:
            Elog._readFlag = self.settings.value("readFlag", set())
            Elog._importantFlag = self.settings.value("importantFlag", set())
            if Elog._readFlag is None or Elog._importantFlag is None:
                raise TypeError
        except TypeError:
            # The list is lost when going from py3 to py2
            logger.error("The previous settings could not be loaded.")
            Elog._readFlag = set()
            Elog._importantFlag = set()

        self.model = QtGui.QStandardItemModel(self.tableView)
        self.model.setItemPrototype(ElogItem())
        self.model.setColumnCount(6)
        self.model.setHorizontalHeaderLabels(
            ["!!", "Category", "Package", "Read", "Highest\neclass", "Date"])

        self.proxyModel = QtCore.QSortFilterProxyModel(self.tableView)
        self.proxyModel.setFilterKeyColumn(-1)
        self.proxyModel.setSourceModel(self.model)
        self.tableView.setModel(self.proxyModel)

        self.proxyModel.setSortRole(Role.SortRole.value)
        horizontalHeader = self.tableView.horizontalHeader()
        horizontalHeader.sortIndicatorChanged.connect(self.proxyModel.sort)

        self.__setupTableColumnDelegates()
        self.tableView.setItemDelegate(ReadFontStyleDelegate(self.tableView))

        self.textEditMapper = QtWidgets.QDataWidgetMapper(self.tableView)
        self.textEditMapper.setSubmitPolicy(self.textEditMapper.AutoSubmit)
        self.textEditMapper.setItemDelegate(
            TextToHtmlDelegate(self.textEditMapper))
        self.textEditMapper.setModel(self.model)
        self.textEditMapper.addMapping(self.textEdit, 0)
        self.tableView.selectionModel().currentRowChanged.connect(
            lambda curr, prev:
            self.textEditMapper.setCurrentModelIndex(_sourceIndex(curr)))
        self.textEditMapper.toFirst()

        self.__initActions()

        self.tableView.selectionModel().currentRowChanged.connect(
            self.onCurrentRowChanged)

        self.searchLineEdit = QtWidgets.QLineEdit(self.toolBar)
        self.searchLineEdit.setPlaceholderText("search")
        self.searchLineEdit.textEdited.connect(
            self.proxyModel.setFilterRegExp)
        self.toolBar.addWidget(self.searchLineEdit)

        def populateAndInit(model, path):
            populate(model, path)
            self.tableView.selectionModel().currentRowChanged.emit(
                QtCore.QModelIndex(), QtCore.QModelIndex())

        QtCore.QTimer.singleShot(0, partial(
            populateAndInit, self.model, self.config.elogpath))

    def __setupTableColumnDelegates(self):
        for column, delegate in (
            (Column.ImportantState, ButtonDelegate(Star(), self.tableView)),
            (Column.ReadState, ButtonDelegate(Bullet(), self.tableView)),
            (Column.Eclass, SeverityColorDelegate(self.tableView)),
        ):
            self.tableView.setItemDelegateForColumn(column.value, delegate)

    def __initActions(self):

        def setToolTip(action):
            if action.shortcut().toString():
                action.setToolTip("%s [%s]" % (
                    action.toolTip(), action.shortcut().toString()))

        self.refreshAction = QtWidgets.QAction("Refresh", self.toolBar)
        self.refreshAction.setIcon(QtGui.QIcon.fromTheme("view-refresh"))
        self.refreshAction.setShortcut(QtGui.QKeySequence.Refresh)
        setToolTip(self.refreshAction)
        self.refreshAction.triggered.connect(self.refresh)
        self.toolBar.addAction(self.refreshAction)

        self.markReadAction = QtWidgets.QAction("Mark read", self.toolBar)
        self.markReadAction.setIcon(
            QtGui.QIcon.fromTheme("mail-mark-read"))
        self.markReadAction.triggered.connect(partial(
            self.setSelectedReadState, Qt.Checked))
        setToolTip(self.markReadAction)
        self.toolBar.addAction(self.markReadAction)

        self.markUnreadAction = QtWidgets.QAction("Mark unread", self.toolBar)
        self.markUnreadAction.setIcon(
            QtGui.QIcon.fromTheme("mail-mark-unread"))
        self.markUnreadAction.triggered.connect(partial(
            self.setSelectedReadState, Qt.Unchecked))
        setToolTip(self.markUnreadAction)
        self.toolBar.addAction(self.markUnreadAction)

        self.markImportantAction = QtWidgets.QAction("Important", self.toolBar)
        self.markImportantAction.setIcon(
            QtGui.QIcon.fromTheme("mail-mark-important"))
        self.markImportantAction.triggered.connect(
            self.toggleSelectedImportantState)
        setToolTip(self.markImportantAction)
        self.toolBar.addAction(self.markImportantAction)

        self.deleteAction = QtWidgets.QAction("Delete", self.toolBar)
        self.deleteAction.setIcon(QtGui.QIcon.fromTheme("edit-delete"))
        self.deleteAction.setShortcut(QtGui.QKeySequence.Delete)
        setToolTip(self.deleteAction)
        self.deleteAction.triggered.connect(self.deleteSelected)
        self.toolBar.addAction(self.deleteAction)

        self.aboutAction = QtWidgets.QAction("About", self.toolBar)
        self.aboutAction.setIcon(QtGui.QIcon.fromTheme("help-about"))
        self.aboutAction.setShortcut(QtGui.QKeySequence.HelpContents)
        setToolTip(self.aboutAction)
        self.aboutAction.triggered.connect(partial(
            QtWidgets.QMessageBox.about,
            self, "About (k)elogviewer", " ".join((
                """
                <h1>(k)elogviewer %s</h1>
                <center><small>(k)elogviewer, copyright (c) 2007, 2011, 2013,
                2015 Mathias Laurin<br>
                kelogviewer, copyright (c) 2007 Jeremy Wickersheimer<br>
                GNU General Public License (GPL) version 2</small><br>
                <a href=http://sourceforge.net/projects/elogviewer>
                http://sourceforge.net/projects/elogviewer</a>
                </center>

                <h2>Written by</h2>
                Mathias Laurin <a href="mailto:mathias_laurin@users.sourceforge.net?Subject=elogviewer">
                &lt;mathias_laurin@users.sourceforge.net&gt;</a><br>
                Timothy Kilbourn (initial author)<br>
                Jeremy Wickersheimer (qt3/KDE port)

                <h2>With contributions from</h2>
                Radice David, gentoo bug #187595<br>
                Christian Faulhammer, gentoo bug #192701

                <h2>Documented by</h2>
                Christian Faulhammer
                <a href="mailto:opfer@gentoo.org">&lt;opfer@gentoo.org&gt;</a>

                """ % __version__).splitlines())))
        self.toolBar.addAction(self.aboutAction)

        self.quitAction = QtWidgets.QAction("Quit", self.toolBar)
        self.quitAction.setIcon(QtGui.QIcon.fromTheme("application-exit"))
        self.quitAction.setShortcut(QtGui.QKeySequence.Quit)
        setToolTip(self.quitAction)
        self.quitAction.triggered.connect(self.close)
        self.toolBar.addAction(self.quitAction)

    def closeEvent(self, closeEvent):
        self.settings.setValue("readFlag", Elog._readFlag)
        self.settings.setValue("importantFlag", Elog._importantFlag)
        super(Elogviewer, self).closeEvent(closeEvent)

    def onCurrentRowChanged(self, current, previous):
        self.setReadState(current, Qt.Checked)
        self.statusLabel.setText(
            "%i of %i elogs" % (current.row() + 1, self.model.rowCount()))
        self.setWindowTitle("Elogviewer (%i unread)" % (
            self.model.rowCount() - len(Elog._readFlag)))
        self.unreadLabel.setText("%i unread" % (
            self.model.rowCount() - len(Elog._readFlag)))

    def setReadState(self, index, state):
        if index.isValid():
            _itemFromIndex(index).setReadState(state)

    def setSelectedReadState(self, state):
        for index in self.tableView.selectionModel().selectedIndexes():
            self.setReadState(index, state)

    def setImportantState(self, index, state):
        if index.isValid():
            _itemFromIndex(index).setImportantState(state)

    def toggleImportantState(self, index):
        if index.isValid():
            _itemFromIndex(index).toggleImportantState()

    def toggleSelectedImportantState(self):
        for index in self.tableView.selectionModel().selectedRows(
                Column.ImportantState.value):
            self.toggleImportantState(index)

    def deleteSelected(self):
        selection = [self.proxyModel.mapToSource(idx) for idx in
                     self.tableView.selectionModel().selectedRows()]
        selectedRows = sorted(idx.row() for idx in selection)
        selectedElogs = [self.model.itemFromIndex(idx).elog()
                         for idx in selection]

        for nRow in reversed(selectedRows):
            self.model.removeRow(nRow)

        for elog in selectedElogs:
            elog.delete()

    def refresh(self):
        self.model.beginResetModel()
        self.model.removeRows(0, self.model.rowCount())
        populate(self.model, self.config.elogpath)
        self.model.endResetModel()


def main():
    parser = argparse.ArgumentParser(description=os.linesep.join(
        """
        Elogviewer should help you not to miss important information.

        You need to enable the elog feature by setting at least one of
        PORTAGE_ELOG_CLASSES="info warn error log qa" and
        PORTAGE_ELOG_SYSTEM="save" in /etc/make.conf.

        You need to add yourself to the portage group to use elogviewer
        without privileges.

        Read /etc/make.conf.example for more information.

        """.splitlines()))
    parser.add_argument("-p", "--elogpath", help="path to the elog directory")
    parser.add_argument("--log", choices="DEBUG INFO WARNING ERROR".split(),
                        default="WARNING", help="set logging level")
    config = parser.parse_args()
    if config.elogpath is None:
        logdir = portage.settings.get(
            "PORT_LOGDIR",
            os.path.join(os.sep, portage.settings["EPREFIX"],
                         *"var/log/portage".split("/")))
        config.elogpath = os.path.join(logdir, "elog")
    logger.setLevel(getattr(logging, config.log))

    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(QtGui.QIcon.fromTheme("applications-system"))

    elogviewer = Elogviewer(config)
    elogviewer.show()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
