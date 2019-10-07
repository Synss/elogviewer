import os
import sys
import unittest
from collections import namedtuple
from glob import glob

import pytest
from PyQt5 import QtCore, QtWidgets

import elogviewer as _ev
from elogviewer import _file, _itemFromIndex

try:
    from unittest import mock
except ImportError:
    from mock import mock


Qt = QtCore.Qt

Column = _ev.Column


config = namedtuple("Config", "elogpath")
config.elogpath = "data"

TEST_SET_SIZE = 5


def _resetTestSet():
    os.system("git checkout -- %s" % config.elogpath)


def _deleteTestSet():
    assert os.getcwd() == os.path.dirname(_ev.__file__)
    os.system("rm -r %s" % config.elogpath)


def _elogs():
    return glob(os.path.join(config.elogpath, "*.log"))


def _htmls():
    return [".".join((os.path.splitext(elog)[0], "html")) for elog in _elogs()]


@pytest.fixture(autouse=True)
def qapp(qtbot):
    pass


@pytest.fixture
def elogviewer():
    elogviewer = _ev.Elogviewer(config)
    elogviewer.populate()
    yield elogviewer
    _resetTestSet()


def _selectFirst(inst):
    inst.tableView.selectionModel().clear()
    inst.tableView.selectRow(0)


def testDeleteTestSet():
    _deleteTestSet()
    assert len(_elogs()) == 0
    assert len(_htmls()) == 0


def testRestTestSet():
    _deleteTestSet()
    _resetTestSet()
    assert len(_elogs()) == TEST_SET_SIZE
    assert len(_htmls()) == TEST_SET_SIZE


def testHasElogs(elogviewer):
    assert elogviewer.elogCount() == len(_elogs()) == TEST_SET_SIZE


def testUnsupportedFormat():
    with _file(_htmls()[0]) as elogfile:
        content = b"".join(elogfile.readlines())
    assert b"ERROR" in content


def testOneRead(elogviewer, qtbot):
    qtbot.mouseClick(elogviewer.markReadButton, Qt.LeftButton)

    elogviewer.readCount() == 1


def testAllRead(elogviewer, qtbot):
    qtbot.keyClick(elogviewer.tableView, Qt.Key_A, Qt.ControlModifier)
    qtbot.mouseClick(elogviewer.markReadButton, Qt.LeftButton)
    elogviewer.readCount() == TEST_SET_SIZE


def testAllUnread(elogviewer, qtbot):
    qtbot.mouseClick(elogviewer.markUnreadButton, Qt.LeftButton)
    elogviewer.readCount() == 0


def testOneImportant(elogviewer, qtbot):
    qtbot.mouseClick(elogviewer.toggleImportantButton, Qt.LeftButton)
    elogviewer.importantCount() == 1


def testAllImportant(elogviewer, qtbot):
    qtbot.keyClick(elogviewer.tableView, Qt.Key_A, Qt.ControlModifier)
    qtbot.mouseClick(elogviewer.toggleImportantButton, Qt.LeftButton)
    elogviewer.importantCount() == TEST_SET_SIZE


def testRefreshButton(elogviewer, qtbot):
    qtbot.keyClick(elogviewer.tableView, Qt.Key_A, Qt.ControlModifier)
    qtbot.mouseClick(elogviewer.deleteButton, Qt.LeftButton)
    _resetTestSet()

    qtbot.mouseClick(elogviewer.refreshButton, Qt.LeftButton)

    assert len(_elogs()) == TEST_SET_SIZE
    assert elogviewer.elogCount() == len(_elogs())


def testDeleteOne(elogviewer, qtbot):
    _selectFirst(elogviewer)
    count = elogviewer.elogCount()

    qtbot.mouseClick(elogviewer.deleteButton, Qt.LeftButton)

    assert count == TEST_SET_SIZE
    assert elogviewer.elogCount() == count - 1
    assert elogviewer.elogCount() == len(_elogs())


def testDeleteTwo(elogviewer, qtbot):
    _selectFirst(elogviewer)
    count = elogviewer.elogCount()

    qtbot.mouseClick(elogviewer.deleteButton, Qt.LeftButton)
    qtbot.mouseClick(elogviewer.deleteButton, Qt.LeftButton)

    assert count == TEST_SET_SIZE
    assert elogviewer.elogCount() == count - 2
    assert elogviewer.elogCount() == len(_elogs())


def testDeleteAll(elogviewer, qtbot):
    qtbot.keyClick(elogviewer.tableView, Qt.Key_A, Qt.ControlModifier)
    qtbot.mouseClick(elogviewer.deleteButton, Qt.LeftButton)

    assert elogviewer.elogCount() == len(_elogs()) == 0


def testDeleteAllPlusOne(elogviewer, qtbot):
    qtbot.keyClick(elogviewer.tableView, Qt.Key_A, Qt.ControlModifier)
    qtbot.mouseClick(elogviewer.deleteButton, Qt.LeftButton)
    assert len(_elogs()) == 0

    qtbot.mouseClick(elogviewer.deleteButton, Qt.LeftButton)

    assert elogviewer.elogCount() == len(_elogs())


def testDecreaseCountOnLeavingRow(elogviewer, qtbot):
    readCount = elogviewer.readCount()

    qtbot.keyClick(elogviewer.tableView, Qt.Key_Down)
    elogviewer.readCount() == readCount + 1
