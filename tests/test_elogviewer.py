import os
from collections import namedtuple
from glob import glob

import pytest
from PyQt5.QtCore import Qt

import elogviewer as _ev
from elogviewer import _file


@pytest.fixture(scope="session")
def elogpath():
    return "data"


@pytest.fixture
def config(elogpath):
    config_ = namedtuple("Config", "elogpath")
    config_.elogpath = elogpath
    return config_


@pytest.fixture
def getElogs(elogpath):
    return lambda: glob(os.path.join(elogpath, "*.log"))


@pytest.fixture
def getHTMLs(getElogs):
    return lambda: [
        ".".join((os.path.splitext(elog)[0], "html")) for elog in getElogs()
    ]


@pytest.fixture
def elogCount(getElogs):
    return len(getElogs())


def testUnsupportedFormat(getHTMLs):
    with _file(getHTMLs()[0]) as elogfile:
        content = b"".join(elogfile.readlines())
    assert b"ERROR" in content


class TestUI:
    @pytest.fixture
    def elogviewer(self, config, qtbot):
        elogviewer = _ev.Elogviewer(config)
        elogviewer.populate()
        qtbot.addWidget(elogviewer)
        yield elogviewer
        os.system("git checkout -- %s" % config.elogpath)
        qtbot.keyClick(elogviewer.tableView, Qt.Key_A, Qt.ControlModifier)
        qtbot.mouseClick(elogviewer.markUnreadButton, Qt.LeftButton)
        qtbot.mouseClick(elogviewer.toggleImportantButton, Qt.LeftButton)
        if elogviewer.importantCount():
            qtbot.mouseClick(elogviewer.toggleImportantButton, Qt.LeftButton)

    def testHasElogs(self, elogviewer, getElogs, elogCount):
        assert elogviewer.elogCount() == len(getElogs()) == elogCount

    def testOneRead(self, elogviewer, qtbot):
        assert elogviewer.readCount() == 0

        qtbot.keyClick(elogviewer.tableView, Qt.Key_Up)
        qtbot.mouseClick(elogviewer.markReadButton, Qt.LeftButton)

        assert elogviewer.readCount() == 1

    def testAllRead(self, elogviewer, elogCount, qtbot):
        assert elogviewer.readCount() == 0

        qtbot.keyClick(elogviewer.tableView, Qt.Key_A, Qt.ControlModifier)
        qtbot.mouseClick(elogviewer.markReadButton, Qt.LeftButton)
        assert elogviewer.readCount() == elogCount

    def testAllUnread(self, elogviewer, elogCount, qtbot):
        qtbot.keyClick(elogviewer.tableView, Qt.Key_Up)
        qtbot.keyClick(elogviewer.tableView, Qt.Key_A, Qt.ControlModifier)
        qtbot.mouseClick(elogviewer.markReadButton, Qt.LeftButton)
        assert elogviewer.readCount() == elogCount

        qtbot.keyClick(elogviewer.tableView, Qt.Key_A, Qt.ControlModifier)
        qtbot.mouseClick(elogviewer.markUnreadButton, Qt.LeftButton)
        assert elogviewer.readCount() == 0

    def testOneImportant(self, elogviewer, qtbot):
        assert elogviewer.importantCount() == 0

        qtbot.keyClick(elogviewer.tableView, Qt.Key_Up)
        qtbot.mouseClick(elogviewer.toggleImportantButton, Qt.LeftButton)

        assert elogviewer.importantCount() == 1

    def testAllImportant(self, elogviewer, elogCount, qtbot):
        assert elogviewer.importantCount() == 0

        qtbot.keyClick(elogviewer.tableView, Qt.Key_A, Qt.ControlModifier)
        qtbot.mouseClick(elogviewer.toggleImportantButton, Qt.LeftButton)

        assert elogviewer.importantCount() == elogCount

    def testRefreshButton(self, elogviewer, elogpath, getElogs, elogCount, qtbot):
        qtbot.keyClick(elogviewer.tableView, Qt.Key_A, Qt.ControlModifier)
        qtbot.mouseClick(elogviewer.deleteButton, Qt.LeftButton)
        os.system("git checkout -- %s" % elogpath)

        qtbot.mouseClick(elogviewer.refreshButton, Qt.LeftButton)

        assert len(getElogs()) == elogCount
        assert elogviewer.elogCount() == len(getElogs())

    def testDeleteOne(self, elogviewer, getElogs, elogCount, qtbot):
        qtbot.keyClick(elogviewer.tableView, Qt.Key_Up)
        count = elogviewer.elogCount()
        assert count == elogCount

        qtbot.mouseClick(elogviewer.deleteButton, Qt.LeftButton)

        assert count == elogCount
        assert elogviewer.elogCount() == count - 1
        assert elogviewer.elogCount() == len(getElogs())

    def testDeleteTwo(self, elogviewer, getElogs, elogCount, qtbot):
        qtbot.keyClick(elogviewer.tableView, Qt.Key_Up)
        count = elogviewer.elogCount()
        assert count == elogCount

        qtbot.mouseClick(elogviewer.deleteButton, Qt.LeftButton)
        qtbot.mouseClick(elogviewer.deleteButton, Qt.LeftButton)

        assert count == elogCount
        assert elogviewer.elogCount() == count - 2
        assert elogviewer.elogCount() == len(getElogs())

    def testDeleteAll(self, elogviewer, getElogs, elogCount, qtbot):
        assert elogviewer.elogCount() == elogCount

        qtbot.keyClick(elogviewer.tableView, Qt.Key_A, Qt.ControlModifier)
        qtbot.mouseClick(elogviewer.deleteButton, Qt.LeftButton)

        assert elogviewer.elogCount() == len(getElogs()) == 0

    def testDeleteAllPlusOne(self, elogviewer, getElogs, elogCount, qtbot):
        assert elogviewer.elogCount() == elogCount

        qtbot.keyClick(elogviewer.tableView, Qt.Key_A, Qt.ControlModifier)
        qtbot.mouseClick(elogviewer.deleteButton, Qt.LeftButton)
        assert len(getElogs()) == 0

        qtbot.mouseClick(elogviewer.deleteButton, Qt.LeftButton)

        assert elogviewer.elogCount() == len(getElogs())

    def testDecreaseCountOnLeavingRow(self, elogviewer, qtbot):
        readCount = elogviewer.readCount()
        assert readCount == 0

        qtbot.keyClick(elogviewer.tableView, Qt.Key_Up)
        qtbot.keyClick(elogviewer.tableView, Qt.Key_Down)

        assert elogviewer.readCount() == readCount + 1
