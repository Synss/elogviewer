import io
import random
import time
from collections import namedtuple
from contextlib import closing
from glob import glob
from pathlib import Path

import pytest
from pyfakefs.fake_filesystem_unittest import Patcher
from PyQt5.QtCore import Qt

import elogviewer as _ev
import tests.fuzz as _fuzz


def randomElogContent(eclass, stage):
    return "\n".join(
        ("{}: {}".format(eclass.value, stage), _fuzz.randomText(5, 10, 10))
    )


def randomElogFileName():
    now = time.gmtime()
    return (
        ":".join(
            (
                "{}-{}".format(_fuzz.randomString(3), _fuzz.randomString(10)),
                "{}-{}.{}.{}".format(
                    _fuzz.randomString(10),
                    random.randint(0, 9),
                    random.randint(0, 9),
                    random.randint(0, 9),
                ),
                time.strftime(
                    "%Y%m%d-%H%M%S", _fuzz.randomTime((now.tm_year - 1, *now[1:]), now)
                ),
            )
        )
        + ".log"
    )


class FakeElog(namedtuple("FakeElog", ["fileName", "content"])):
    pass


def _count(iterable):
    return sum(1 for _ in iterable)


@pytest.fixture(scope="session")
def elogPath():
    with Patcher():
        return Path("/var/log/portage/elog/")


@pytest.fixture(scope="session")
def elogFiles():
    elogs = []
    for eclass in _ev.EClass:
        for _ in range(5):
            elogs.append(
                FakeElog(
                    randomElogFileName(),
                    randomElogContent(eclass, _fuzz.randomString(10)),
                )
            )
    return elogs


@pytest.fixture
def elogsToFS(fs, elogPath, elogFiles):
    for fakeElog in elogFiles:
        fs.create_file(elogPath / fakeElog.fileName, contents=fakeElog.content)
    assert _count(elogPath.glob("*")) == len(elogFiles)


@pytest.fixture
def getHTMLs():
    pass


@pytest.fixture
def elogCount(elogFiles):
    return len(elogFiles)


@pytest.mark.skip
def testUnsupportedFormat(getHTMLs):
    with _ev.Elog._file(getHTMLs()[0]) as elogfile:
        content = b"".join(elogfile.readlines())
    assert b"ERROR" in content


class TestParserFSM:
    @pytest.fixture
    def results(self):
        return []

    @pytest.fixture
    def parser(self, results):
        with _ev.ParserFSM(results) as parser:
            yield parser

    def testSmokeTestParserStr(self, parser):
        assert isinstance(str(parser), str)

    @pytest.mark.parametrize("state", [_ev.NoopState, _ev.HeaderState, _ev.BodyState])
    def testSmokeTestStateStr(self, parser, state):
        assert isinstance(str(state(parser)), str)

    def testParseNotAHeader(self, parser, results):
        # Gentoo Bug 721522
        for line in "LOG: xxx\nSection content".splitlines():
            # Initialize FSM
            parser.parse(line)
        assert type(parser.state) is _ev.BodyState

        # Looks like a header but is not.
        line = "ERROR: dev-python/sqlalchemy-migrate-0.13.0::gentoo failed (prepare phase):"
        parser.parse(line)

        assert type(parser.state) is _ev.BodyState


class TestElogClassUnit:
    @pytest.mark.parametrize("eclass", _ev.EClass)
    def testGetClassValue(self, eclass):
        content = "{}: xxx\n".format(eclass.value)
        assert _ev.Elog.getClass(content) is eclass

    @pytest.mark.parametrize("eclass", _ev.EClass)
    def testGetClassWrongCaseDoesNotMatch(self, eclass):
        content = "QA: xxx\n{}: xxx".format(eclass.value.lower())
        assert _ev.Elog.getClass(content) is _ev.EClass.QA

    def testGetClassDefaultsToLog(self):
        content = "XXX: xxx\nXXX: xxx"
        assert _ev.Elog.getClass(content) is _ev.EClass.Log

    @pytest.mark.parametrize(
        "content, eclass",
        [
            ("LOG: xxx\nWARN: xxx\n", _ev.EClass.Warning),
            ("QA: xxx\nWARN: xxx\nERROR: xxx\n", _ev.EClass.Error),
            ("QA: xxx\nWARN: xxx\nError: xxx\n", _ev.EClass.Warning),
            ("QA: xxx\nINFO: xxx\nINFO: xxx", _ev.EClass.Info),
        ],
    )
    def testGetClassMisc(self, content, eclass):
        assert _ev.Elog.getClass(content) is eclass


class TestElogClass:
    @pytest.fixture(params=_ev.EClass)
    def eclass(self, request):
        return request.param

    @pytest.fixture
    def elogFile(self, eclass):
        return FakeElog(
            randomElogFileName(), randomElogContent(eclass, _fuzz.randomString(10))
        )

    @pytest.fixture
    def elogFullPath(self, elogPath, elogFile):
        return elogPath / elogFile.fileName

    @pytest.fixture
    def elogContents(self, elogFile):
        return elogFile.content

    @pytest.fixture
    def elogClassInstance(self, elogFullPath, elogFile, fs):
        fs.create_file(elogFullPath, contents=elogFile.content)
        return _ev.Elog.fromFilename(elogFullPath)

    def testFileName(self, elogClassInstance, elogFullPath):
        assert elogClassInstance.filename == elogFullPath

    def testContents(self, elogClassInstance, elogContents):
        assert elogClassInstance.contents == elogContents

    def testEClass(self, elogClassInstance, eclass, elogFile):
        assert elogClassInstance.eclass is eclass

    @pytest.mark.parametrize(
        "elogText, elogHtml",
        [
            # Regular logs
            (
                "ERROR: error_stage\ntext",
                "<h2>\n"
                "Error:  error_stage\n\n"
                "</h2>\n"
                '<p style="color: #ff0000">\n'
                "text <br />\n"
                "</p>",
            ),
            # Bugs
            (
                "bug #42",
                '<p style="color: #008000">\n'
                '<a href="https://bugs.gentoo.org/42">bug #42</a> <br />\n'
                "</p>",
            ),
            (
                "Bug #42",
                '<p style="color: #008000">\n'
                '<a href="https://bugs.gentoo.org/42">Bug #42</a> <br />\n'
                "</p>",
            ),
            (
                "text bug #42 text",
                '<p style="color: #008000">\n'
                'text <a href="https://bugs.gentoo.org/42">bug #42</a> text <br />\n'
                "</p>",
            ),
            # Hyperlinks
            (
                "text http://example.com/url text",
                '<p style="color: #008000">\n'
                'text <a href="http://example.com/url">http://example.com/url</a> text <br />\n'
                "</p>",
            ),
            # Packages
            (
                "text dev-portage/elogviewer-3.0 text",
                '<p style="color: #008000">\n'
                'text <a href="http://packages.gentoo.org/packages/dev-portage/elogviewer">dev-portage/elogviewer-3.0</a> text <br />\n'
                "</p>",
            ),
        ],
    )
    def testHtml(self, elogText, elogHtml, monkeypatch):
        monkeypatch.setattr(_ev.Elog, "file", closing(io.StringIO(elogText)))
        elog = _ev.Elog("", "", "", "", "")
        assert elog.html == elogHtml


@pytest.mark.usefixtures("elogsToFS")
class TestUI:
    @pytest.fixture
    def config(self, elogPath):
        config_ = namedtuple("Config", "elogpath")
        config_.elogpath = elogPath
        return config_

    @pytest.fixture
    def elogviewer(self, config, qtbot, qtmodeltester):
        elogviewer = _ev.Elogviewer(config)
        elogviewer.populate()
        qtbot.addWidget(elogviewer)
        yield elogviewer
        qtmodeltester.check(elogviewer.model)
        qtbot.keyClick(elogviewer.tableView, Qt.Key_A, Qt.ControlModifier)
        qtbot.mouseClick(elogviewer.markUnreadButton, Qt.LeftButton)
        qtbot.mouseClick(elogviewer.toggleImportantButton, Qt.LeftButton)
        if elogviewer.importantCount():
            qtbot.mouseClick(elogviewer.toggleImportantButton, Qt.LeftButton)

    def testHasElogs(self, elogviewer, elogPath, elogCount):
        assert _count(elogPath.glob("*.log")) == elogCount
        assert elogviewer.elogCount() == elogCount

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

    @pytest.mark.skip
    def testRefreshButton(self, elogviewer, elogPath, elogCount, qtbot):
        qtbot.keyClick(elogviewer.tableView, Qt.Key_A, Qt.ControlModifier)
        qtbot.mouseClick(elogviewer.deleteButton, Qt.LeftButton)

        qtbot.mouseClick(elogviewer.refreshButton, Qt.LeftButton)

        assert _count(elogPath.glob("*.log")) == elogCount
        assert elogviewer.elogCount() == elogCount

    def testDeleteOne(self, elogviewer, elogPath, elogCount, qtbot):
        qtbot.keyClick(elogviewer.tableView, Qt.Key_Up)
        count = elogviewer.elogCount()
        assert count == elogCount

        qtbot.mouseClick(elogviewer.deleteButton, Qt.LeftButton)

        assert count == elogCount
        assert elogviewer.elogCount() == count - 1
        assert elogviewer.elogCount() == _count(elogPath.glob("*.log"))

    def testDeleteTwo(self, elogviewer, elogPath, elogCount, qtbot):
        qtbot.keyClick(elogviewer.tableView, Qt.Key_Up)
        count = elogviewer.elogCount()
        assert count == elogCount

        qtbot.mouseClick(elogviewer.deleteButton, Qt.LeftButton)
        qtbot.mouseClick(elogviewer.deleteButton, Qt.LeftButton)

        assert count == elogCount
        assert elogviewer.elogCount() == count - 2
        assert elogviewer.elogCount() == _count(elogPath.glob("*.log"))

    def testDeleteAll(self, elogviewer, elogPath, elogCount, qtbot):
        assert elogviewer.elogCount() == elogCount

        qtbot.keyClick(elogviewer.tableView, Qt.Key_A, Qt.ControlModifier)
        qtbot.mouseClick(elogviewer.deleteButton, Qt.LeftButton)

        assert elogviewer.elogCount() == _count(elogPath.glob("*.log")) == 0

    def testDeleteAllPlusOne(self, elogviewer, elogPath, elogCount, qtbot):
        assert elogviewer.elogCount() == elogCount

        qtbot.keyClick(elogviewer.tableView, Qt.Key_A, Qt.ControlModifier)
        qtbot.mouseClick(elogviewer.deleteButton, Qt.LeftButton)
        assert _count(elogPath.glob("*.log")) == 0

        qtbot.mouseClick(elogviewer.deleteButton, Qt.LeftButton)

        assert elogviewer.elogCount() == _count(elogPath.glob("*.log"))

    def testDecreaseCountOnLeavingRow(self, elogviewer, qtbot):
        readCount = elogviewer.readCount()
        assert readCount == 0

        qtbot.keyClick(elogviewer.tableView, Qt.Key_Up)
        qtbot.keyClick(elogviewer.tableView, Qt.Key_Down)

        assert elogviewer.readCount() == readCount + 1
