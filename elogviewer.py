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

"""
Elogviewer should help you not to miss important information.

You need to enable the elog feature by setting at least one of
PORTAGE_ELOG_CLASSES="info warn error log qa" and
PORTAGE_ELOG_SYSTEM="save" in /etc/make.conf.

You need to add yourself to the portage group to use elogviewer
without privileges.

Read /etc/make.conf.example for more information.
"""

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
from collections import namedtuple
from contextlib import closing

from enum import IntEnum
from io import BytesIO

import gzip
import bz2
try:
    import liblzma as lzma
except ImportError:
    lzma = None

try:
    import sip
except ImportError:
    from PySide import QtGui, QtCore
    QtCore.QSortFilterProxyModel = QtGui.QSortFilterProxyModel
    QtWidgets = QtGui
else:
    try:
        from PyQt5 import QtGui, QtWidgets, QtCore
    except ImportError:
        for type in "QDate QDateTime QString QVariant".split():
            sip.setapi(type, 2)
        from PyQt4 import QtGui, QtCore
        QtCore.QSortFilterProxyModel = QtGui.QSortFilterProxyModel
        QtWidgets = QtGui
        del type
    finally:
        del sip

Qt = QtCore.Qt

try:
    import portage
except ImportError:
    portage = None


__version__ = "2.6"


def _(bytes):
    """This helper changes `bytes` to `str` on python3 and does nothing
    under python2.

    """
    return bytes.decode(locale.getpreferredencoding(), "replace")


class Role(IntEnum):

    SortRole = Qt.UserRole + 1


# [Fonic] Reorder/rename columns, add column 'Logfile'
class Column(IntEnum):

    ImportantState = 0
    ReadState      = 1
    Category       = 2
    Package        = 3
    Eclass         = 4
    Date           = 5
    LogFile        = 6


# [Fonic] Reorder/rename eclasses, add colors, change htmlColor()
class EClass(IntEnum):

    Error   = 4
    Warning = 3
    Log     = 2
    Info    = 1
    QA      = 0

    def color(self):
        return dict(
            Error   = QtGui.QColor(Qt.red),
            Warning = QtGui.QColor(229, 103, 23),
            Info    = QtGui.QColor(Qt.darkGreen),
            Log     = QtGui.QColor(Qt.darkGreen),
            QA      = QtGui.QColor(Qt.darkGreen)
        ).get(self.name, QtGui.QPalette().color(QtGui.QPalette.Text))

    def htmlColor(self):
        return self.color().name()


def _sourceIndex(index):
    model = index.model()
    try:
        index = model.mapToSource(index)  # proxy
    except AttributeError:
        pass
    return index


def _itemFromIndex(index):
    if index.isValid():
        index = _sourceIndex(index)
        return index.model().itemFromIndex(index)
    else:
        return ElogItem()


def _file(filename):
        root, ext = os.path.splitext(filename)
        try:
            return {".gz":  gzip.open,
                    ".bz2": bz2.BZ2File,
                    ".log": open}[ext](filename, "rb")
        except KeyError:
            logger.error("%s: unsupported format" % filename)
            return closing(BytesIO(
                b"""
                <!-- set eclass: ERROR: -->
                <h3>Unsupported format</h3>
                The selected elog is in an unsupported format.
                """
            ))
        except IOError:
            logger.error("%s: could not open file" % filename)
            return closing(BytesIO(
                b"""
                <!-- set eclass: ERROR: -->
                <h3>File does not open</h3>
                The selected elog could not be opened.
                """
            ))


def _html(filename):
    lines = []
    with _file(filename) as elogfile:
        for line in elogfile:
            line = _(line.strip())
            try:
                # Identify section headers
                eclass, stage = line.split(":")
                if eclass == "ERROR":
                    eclass = EClass.Error
                elif eclass == "WARN":
                    eclass = EClass.Warning
                elif eclass == "LOG":
                    eclass = EClass.Log
                elif eclass == "INFO":
                    eclass = EClass.Info
                elif eclass == "QA":
                    eclass = EClass.QA
                else:
                    raise ValueError
            except ValueError:
                # Not a section header, just write line
                lines.append("{} <br />".format(line))
            else:
                # Format section header
                sectionHeader = "".join((
                    "<h3 style=\"color: {color}\">{eclass}: {stage}</h3>".format(
                        color=eclass.htmlColor(),
                        #eclass=eclass.name[1:].capitalize(),
                        eclass=eclass.name,
                        stage=stage
                    ),
                    "<p style=\"color: {}\">".format(eclass.htmlColor())))
                # Close previous section if exists and open new section
                if lines:
                    lines.append("</p>")
                lines.append(sectionHeader)
    lines.append("</p>")
    lines.append("")
    text = os.linesep.join(lines)
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
        "(\s)([a-z1]+[-][a-z0-9]+/[a-z0-9-]+)([\s,.:;!?])",
        r'\1<a href="http://packages.gentoo.org/package/\2">\2</a>\3',
        text)
    return text


class Elog(namedtuple("Elog", ["filename", "category", "package",
                               "date", "eclass"])):

    @classmethod
    def fromFilename(cls, filename):
        basename = os.path.basename(filename)
        try:
            category, package, rest = basename.split(":")
        except ValueError:
            category = os.path.dirname(filename).split(os.sep)[-1]
            package, rest = basename.split(":")
        date = rest.split(".")[0]
        date = time.strptime(date, "%Y%m%d-%H%M%S")
        # Get the highest elog class. Adapted from Luca Marturana's elogv.
        with _file(filename) as elogfile:
            eClasses = re.findall("ERROR:|WARN:|LOG:|INFO:|QA:", _(elogfile.read()))
            if "ERROR:" in eClasses:
                eclass = EClass.Error
            elif "WARN:" in eClasses:
                eclass = EClass.Warning
            elif "LOG:" in eClasses:
                eclass = EClass.Log
            elif "INFO:" in eClasses:
                eclass = EClass.Info
            elif "QA:" in eClasses:
                eclass = EClass.QA
            else:
                eclass = EClass.Info
        return cls(filename, category, package, date, eclass)

    @property
    def isoTime(self):
        return time.strftime("%Y-%m-%d %H:%M:%S", self.date)

    @property
    def localeTime(self):
        return time.strftime("%x %X", self.date)


class TextToHtmlDelegate(QtWidgets.QItemDelegate):

    def __init__(self, parent=None):
        super(TextToHtmlDelegate, self).__init__(parent)

    def __repr__(self):
        return "elogviewer.%s(%r)" % (self.__class__.__name__, self.parent())

    def setEditorData(self, editor, index):
        if not index.isValid() or not isinstance(editor, QtWidgets.QTextEdit):
            return
        model = index.model()
        editor.setHtml(model.itemFromIndex(index).html())


class SeverityColorDelegate(QtWidgets.QStyledItemDelegate):

    def __init__(self, parent=None):
        super(SeverityColorDelegate, self).__init__(parent)

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
        super(SeverityColorDelegate, self).paint(painter, option, index)


class ReadFontStyleDelegate(QtWidgets.QStyledItemDelegate):

    def __init__(self, parent=None):
        super(ReadFontStyleDelegate, self).__init__(parent)

    def paint(self, painter, option, index):
        if not index.isValid():
            return
        self.initStyleOption(option, index)
        option.font.setBold(_itemFromIndex(index).readState() is Qt.Unchecked)
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
            self._starPolygon.append(QtCore.QPointF(
                0.5 + 0.5 * cos(0.8 * i * 3.14),
                0.5 + 0.5 * sin(0.8 * i * 3.14))
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
        super(ButtonDelegate, self).__init__(parent)
        self._btn = QtWidgets.QPushButton() if button is None else button
        self._btn.setCheckable(True)
        self._btn.setParent(parent)
        self._btn.hide()

    def __repr__(self):
        return "elogviewer.%s(button=%r, parent=%r)" % (
            self.__class__.__name__, self._btn, self.parent())

    def sizeHint(self, option, index):
        return super(ButtonDelegate, self).sizeHint(option, index)

    def createEditor(self, parent, option, index):
        return None

    def setModelData(self, editor, model, index):
        data = Qt.Checked if editor.isChecked() else Qt.Unchecked
        model.setData(index, data, role=Qt.CheckStateRole)

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


class ElogRowItem(QtGui.QStandardItem):

    def __init__(self, filename="", parent=None):
        super(ElogRowItem, self).__init__(parent)
        self._elog = Elog.fromFilename(filename) if filename else Elog(
            "", None, None, time.localtime(), EClass.Info)
        self._readState = Qt.Unchecked
        self._importantState = Qt.Unchecked

    def type(self):
        return self.UserType + 1

    def clone(self):
        return self.__class__()

    def filename(self):
        return self._elog.filename

    def html(self):
        header = "<h2>{category}/{package}</h2>".format(
            category=self._elog.category,
            package=self._elog.package,
        )
        text = _html(self._elog.filename)
        return header + text

    def setReadState(self, state):
        self._readState = state
        self.emitDataChanged()

    def readState(self):
        return self._readState

    def setImportantState(self, state):
        self._importantState = state
        self.emitDataChanged()

    def importantState(self):
        return self._importantState

    def isImportantState(self):
        return self.importantState() is Qt.Checked

    def toggleImportantState(self):
        self.setImportantState(Qt.Unchecked if self.isImportantState() else
                               Qt.Checked)


class ElogItem(QtGui.QStandardItem):

    def __init__(self, parent=None):
        super(ElogItem, self).__init__(parent)

    def type(self):
        return self.UserType + 2

    def clone(self):
        return self.__class__()

    def __getattr__(self, name):

        def verticalHeaderItem():
            try:
                item = self.model().verticalHeaderItem(self.row())
            except AttributeError:
                assert(self.model() is None)
                item = None
            return item if item else ElogRowItem()

        return getattr(verticalHeaderItem(), name)

    def setData(self, value, role=Qt.UserRole + 1):
        if role == Qt.CheckStateRole:
            return {
                Column.ImportantState: self.setImportantState,
                Column.ReadState: self.setReadState,
            }.get(self.column(), lambda: None)(value)
        super(ElogItem, self).setData(value, role)

    def data(self, role=Qt.UserRole + 1):
        elog = self._elog
        if not elog:
            return super(ElogItem, self).data(role)
        if role in (Qt.DisplayRole, Qt.EditRole):
            return {
                Column.Category: elog.category,
                Column.Package: elog.package,
                #
                Column.Eclass: elog.eclass.name,
                Column.Date: elog.localeTime,
                # [Fonic] Add column 'Logfile'
                Column.LogFile: os.path.basename(elog.filename)
            }.get(self.column(), "")
        elif role == Qt.CheckStateRole:
            return {
                Column.ImportantState: self.importantState,
                Column.ReadState: self.readState,
            }.get(self.column(), lambda: None)()
        elif role == Role.SortRole:
            if self.column() in (Column.ImportantState, Column.ReadState):
                return self.data(Qt.CheckStateRole)
            elif self.column() == Column.Date:
                return elog.isoTime
            elif self.column() == Column.Eclass:
                return elog.eclass.value
            else:
                return self.data(Qt.DisplayRole)
        else:
            return super(ElogItem, self).data(role)


class ElogviewerUi(QtWidgets.QMainWindow):

    def __init__(self):
        super(ElogviewerUi, self).__init__()
        centralWidget = QtWidgets.QWidget(self)
        centralLayout = QtWidgets.QVBoxLayout()
        centralWidget.setLayout(centralLayout)
        self.setCentralWidget(centralWidget)

        self.tableView = QtWidgets.QTableView(centralWidget)
        self.tableView.setSortingEnabled(True)
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
        self.settings = QtCore.QSettings("elogviewer", "elogviewer")
        if not self.settings.contains("readFlag"):
            self.settings.setValue("readFlag", set())
        if not self.settings.contains("importantFlag"):
            self.settings.setValue("importantFlag", set())
        if self.settings.contains("windowWidth") and self.settings.contains("windowHeight"):
            self.resize(int(self.settings.value("windowWidth")), int(self.settings.value("windowHeight")))
        else:
            screenSize = QtWidgets.QApplication.desktop().screenGeometry()
            self.resize(screenSize.width() / 2, screenSize.height() / 2)

        self.model = QtGui.QStandardItemModel(self.tableView)
        # Use QStandardItem for horizontal headers
        # [Fonic] Reorder/rename columns, add column 'Logfile'
        self.model.setHorizontalHeaderLabels(
            ["!!", "Read", "Category", "Package", "Type", "Date", "Logfile"])
        # Then default to ElogItem -- else, the labels are not displayed
        self.model.setItemPrototype(ElogItem())

        self.proxyModel = QtCore.QSortFilterProxyModel(self.tableView)
        self.proxyModel.setFilterKeyColumn(-1)
        self.proxyModel.setSourceModel(self.model)
        self.tableView.setModel(self.proxyModel)

        self.proxyModel.setSortRole(Role.SortRole)
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

        self.__initActions()

        self.tableView.selectionModel().currentRowChanged.connect(
            self.onCurrentRowChanged)

        self.searchLineEdit = QtWidgets.QLineEdit(self.toolBar)
        self.searchLineEdit.setPlaceholderText("search")
        self.searchLineEdit.textEdited.connect(
            self.proxyModel.setFilterRegExp)
        self.toolBar.addWidget(self.searchLineEdit)

        self.populate()
        if self.settings.contains("sortColumn") and self.settings.contains("sortOrder"):
            self.tableView.sortByColumn(int(self.settings.value("sortColumn")), int(self.settings.value("sortOrder")))
        else:
            self.tableView.sortByColumn(Column.Date, Qt.DescendingOrder)
        self.tableView.selectRow(0)

    def __setupTableColumnDelegates(self):
        for column, delegate in (
            (Column.ImportantState, ButtonDelegate(Star(), self.tableView)),
            (Column.ReadState, ButtonDelegate(Bullet(), self.tableView)),
            (Column.Eclass, SeverityColorDelegate(self.tableView)),
        ):
            self.tableView.setItemDelegateForColumn(column, delegate)

    def __initActions(self):

        def setToolTip(action):
            if action.shortcut().toString():
                action.setToolTip("%s [%s]" % (
                    action.toolTip(), action.shortcut().toString()))

        Icon = QtGui.QIcon.fromTheme

        self.refreshAction = QtWidgets.QAction("Refresh", self.toolBar)
        self.refreshAction.setIcon(Icon("view-refresh"))
        self.refreshAction.setShortcut(QtGui.QKeySequence.Refresh)
        setToolTip(self.refreshAction)
        self.refreshAction.triggered.connect(self.refresh)
        self.toolBar.addAction(self.refreshAction)

        self.markReadAction = QtWidgets.QAction("Mark read", self.toolBar)
        self.markReadAction.setIcon(Icon("mail-mark-read"))
        self.markReadAction.triggered.connect(partial(
            self.setSelectedReadState, Qt.Checked))
        setToolTip(self.markReadAction)
        self.toolBar.addAction(self.markReadAction)

        self.markUnreadAction = QtWidgets.QAction("Mark unread", self.toolBar)
        self.markUnreadAction.setIcon(Icon("mail-mark-unread"))
        self.markUnreadAction.triggered.connect(partial(
            self.setSelectedReadState, Qt.Unchecked))
        setToolTip(self.markUnreadAction)
        self.toolBar.addAction(self.markUnreadAction)

        self.markImportantAction = QtWidgets.QAction("Important", self.toolBar)
        self.markImportantAction.setIcon(Icon("mail-mark-important"))
        self.markImportantAction.triggered.connect(
            self.toggleSelectedImportantState)
        setToolTip(self.markImportantAction)
        self.toolBar.addAction(self.markImportantAction)

        self.deleteAction = QtWidgets.QAction("Delete", self.toolBar)
        self.deleteAction.setIcon(Icon("edit-delete"))
        self.deleteAction.setShortcut(QtGui.QKeySequence.Delete)
        setToolTip(self.deleteAction)
        self.deleteAction.triggered.connect(self.deleteSelected)
        self.toolBar.addAction(self.deleteAction)

        self.aboutAction = QtWidgets.QAction("About", self.toolBar)
        self.aboutAction.setIcon(Icon("help-about"))
        self.aboutAction.setShortcut(QtGui.QKeySequence.HelpContents)
        setToolTip(self.aboutAction)
        self.aboutAction.triggered.connect(partial(
            QtWidgets.QMessageBox.about,
            self, "About (k)elogviewer", " ".join((
                """
                <h1>(k)elogviewer %s</h1>
                (k)elogviewer, copyright (c) 2007, 2011, 2013,
                2015 Mathias Laurin<br>
                kelogviewer, copyright (c) 2007 Jeremy Wickersheimer<br>
                GNU General Public License (GPL) version 2<br>
                <a href=http://sourceforge.net/projects/elogviewer>
                http://sourceforge.net/projects/elogviewer</a>

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
        self.quitAction.setIcon(Icon("application-exit"))
        self.quitAction.setShortcut(QtGui.QKeySequence.Quit)
        setToolTip(self.quitAction)
        self.quitAction.triggered.connect(self.close)
        self.toolBar.addAction(self.quitAction)

    def saveSettings(self):
        readFlag = set()
        importantFlag = set()
        for row in range(self.model.rowCount()):
            item = self.model.item(row, Column.ReadState)
            if item.readState() is Qt.Checked:
                readFlag.add(item.filename())
            if item.importantState() is Qt.Checked:
                importantFlag.add(item.filename())
        self.settings.setValue("readFlag", readFlag)
        self.settings.setValue("importantFlag", importantFlag)
        self.settings.setValue("sortColumn", self.tableView.horizontalHeader().sortIndicatorSection())
        self.settings.setValue("sortOrder", self.tableView.horizontalHeader().sortIndicatorOrder())
        self.settings.setValue("windowWidth", self.width())
        self.settings.setValue("windowHeight", self.height())

    def closeEvent(self, closeEvent):
        self.saveSettings()
        super(Elogviewer, self).closeEvent(closeEvent)

    def onCurrentRowChanged(self, current, previous):
        if (previous.row() != -1):
            currentItem, previousItem = map(_itemFromIndex, (current, previous))
            if currentItem.readState() is Qt.Unchecked:
                currentItem.setReadState(Qt.PartiallyChecked)
            if previousItem.readState() is Qt.PartiallyChecked:
                previousItem.setReadState(Qt.Checked)
        self.updateStatus()
        self.updateUnreadCount()

    def updateStatus(self):
        text = "%i of %i elogs" % (self.currentRow() + 1, self.elogCount())
        self.statusLabel.setText(text)

    def updateUnreadCount(self):
        text = "[%i unread]" % self.unreadCount()
        self.unreadLabel.setText(text)
        self.setWindowTitle("Elogviewer (%s)" % text)

    def currentRow(self):
        return self.tableView.selectionModel().currentIndex().row()

    # [Fonic] Set current row
    def setCurrentRow(self, index):
        self.tableView.selectionModel().setCurrentIndex(index, QtCore.QItemSelectionModel.Select)

    # [Fonic] Remove row
    def removeRow(self, index):
        self.model.removeRow(index.row())

    def rowCount(self):
        return self.proxyModel.rowCount()

    def elogCount(self):
        return self.model.rowCount()

    def readCount(self):
        count = 0
        for row in range(self.model.rowCount()):
            if self.model.item(row, 0).readState() is not Qt.Unchecked:
                count += 1
        return count

    def unreadCount(self):
        return self.elogCount() - self.readCount()

    def setSelectedReadState(self, state):
        for index in self.tableView.selectionModel().selectedIndexes():
            _itemFromIndex(index).setReadState(state)
        self.updateUnreadCount()

    def importantCount(self):
        count = 0
        for row in range(self.model.rowCount()):
            if self.model.item(row, 0).importantState() is Qt.Checked:
                count += 1
        return count

    def toggleSelectedImportantState(self):
        for index in self.tableView.selectionModel().selectedRows(
                Column.ImportantState):
            _itemFromIndex(index).toggleImportantState()


    # [Fonic] Reworked delete logic
    def deleteSelected(self):

        # Remember row after the one that was added last to the selection
        # (which isn't necessarily the bottommost one, e.g. when selecting
        # using CTRL)
        selection = self.tableView.selectionModel().selectedRows()
        savedrow = selection[len(selection)-1].row() + 1

        # Keep processing selected rows:
        #   - get index of first non-skipped selected row
        #   - map index to source
        #   - get item from index, get associated filename
        #   - set current row (-> scroll to current item and display it in reading pane)
        #   - try:
        #     - delete logfile (if existing; if not, don't care)
        #     - decrease savedrow if deleted row is located above (since table is about to shrink)
        #     - remove row from table
        #   - except:
        #     - increase number of skipped rows
        #     - open messagebox displaying error, user may continue or abort
        # until there are no non-skipped selected rows left
        skipped = 0
        selection = self.tableView.selectionModel().selectedRows()
        while (len(selection) > skipped):
            index = selection[0+skipped]
            mapped = self.proxyModel.mapToSource(index)
            filename = self.model.itemFromIndex(mapped).filename()

            self.setCurrentRow(mapped)
            self.tableView.scrollTo(index, QtWidgets.QAbstractItemView.PositionAtCenter)

            try:
                if os.path.exists(filename):
                    os.remove(filename)
                if (index.row() < savedrow):
                    savedrow -= 1
                self.removeRow(mapped)
                selection = self.tableView.selectionModel().selectedRows()

            except IOError as ioerr:
                skipped += 1
                messagebox = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Critical, "Error", "Error while trying to delete '%s':<br><b>%s</b>" % (filename, ioerr.strerror), QtWidgets.QMessageBox.NoButton, self)
                button1 = messagebox.addButton("Continue", QtWidgets.QMessageBox.AcceptRole)
                button2 = messagebox.addButton("Abort", QtWidgets.QMessageBox.RejectRole)
                if (len(selection) - skipped == 0):
                    button1.setText("Close")
                    button2.setEnabled(False)
                if (messagebox.exec() == QtWidgets.QMessageBox.RejectRole):
                    break

        # Check selection
        if (len(selection) > 0):
            # Still items selected, i.e. at least one deletion failed.
            # Keep selection, set current row to the one that was last
            # added to the selection
            self.setCurrentRow(selection[len(selection)-1])
        else:
            # Nothing selected, i.e. all previously selected items were
            # deleted. Set current row to remembered row (see beginning
            # of method)
            self.tableView.selectionModel().reset()
            self.tableView.selectRow(min(savedrow, self.rowCount()-1))


    def refresh(self):
        self.saveSettings()
        self.populate()

    def populate(self):
        currentRow = self.currentRow()
        self.tableView.selectionModel().reset()
        self.model.beginResetModel()
        # Clear
        self.model.removeRows(0, self.model.rowCount())
        # Populate
        for row, filename in enumerate(
                glob(os.path.join(self.config.elogpath, "*:*:*.log*")) +
                glob(os.path.join(self.config.elogpath, "*", "*:*.log*"))):
            elogRowItem = ElogRowItem(filename)
            elogRowItem.setReadState(
                Qt.Checked
                if filename in self.settings.value("readFlag")
                else Qt.Unchecked)
            elogRowItem.setImportantState(
                Qt.Checked
                if filename in self.settings.value("importantFlag")
                else Qt.Unchecked)
            self.model.setVerticalHeaderItem(row, elogRowItem)
            for column in range(self.model.columnCount()):
                item = ElogItem()
                item.setEditable(column == Column.ImportantState)
                self.model.setItem(row, column, item)
        self.model.endResetModel()
        self.tableView.selectRow(min(currentRow, self.rowCount() - 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-p", "--elogpath", help="path to the elog directory")
    parser.add_argument("--log", choices="DEBUG INFO WARNING ERROR".split(),
                        default="WARNING", help="set logging level")
    config = parser.parse_args()
    if portage and not config.elogpath:
        logdir = portage.settings.get(
            "PORT_LOGDIR",
            os.path.join(os.sep, portage.settings["EPREFIX"],
                         *"var/log/portage".split("/")))
        config.elogpath = os.path.join(logdir, "elog")
    else:
        config.elogpath = ""
    logger.setLevel(getattr(logging, config.log))

    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(QtGui.QIcon.fromTheme("applications-system"))

    elogviewer = Elogviewer(config)
    elogviewer.show()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
