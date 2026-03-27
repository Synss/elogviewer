from __future__ import annotations

import io
import random
import time
from collections.abc import Iterable, Iterator, Sequence
from contextlib import closing
from pathlib import Path
from typing import Any, NamedTuple

import pytest  # type: ignore
from pyfakefs.fake_filesystem_unittest import Patcher  # type: ignore
from PyQt6.QtCore import Qt

import elogviewer as _ev
import fuzz as _fuzz


def randomElogContent(eclass: _ev.EClass, stage: str) -> str:
    return "\n".join(
        ("{}: {}".format(eclass.value, stage), _fuzz.randomText(5, 10, 10))
    )


def randomElogFileName() -> str:
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


class FakeElog(NamedTuple):
    fileName: str
    content: str


def _count(iterable: Iterable[object]) -> int:
    return sum(1 for _ in iterable)


@pytest.fixture()
def elogPath() -> Iterator[Path]:
    with Patcher():
        yield Path("/var/log/portage/elog/")


@pytest.fixture()
def elogFiles() -> Sequence[FakeElog]:
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
def elogsToFS(fs: Any, elogPath: Path, elogFiles: Sequence[FakeElog]) -> None:
    for fakeElog in elogFiles:
        fs.create_file(elogPath / fakeElog.fileName, contents=fakeElog.content)
    assert _count(elogPath.glob("*")) == len(elogFiles)


@pytest.fixture
def getHTMLs() -> None:
    pass


@pytest.fixture
def elogCount(elogFiles: Sequence[FakeElog]) -> int:
    return len(elogFiles)


@pytest.mark.skip
def testUnsupportedFormat(getHTMLs: None) -> None:
    with _ev.Elog._file(getHTMLs()[0]) as elogfile:  # type: ignore
        content = b"".join(elogfile.readlines())
    assert b"ERROR" in content


class TestParserFSM:
    @pytest.fixture
    def results(self) -> list[str | None]:
        return []

    @pytest.fixture
    def parser(self, results: list[str | None]) -> Iterator[_ev.ParserFSM]:
        with _ev.ParserFSM(results) as parser:
            yield parser

    def testSmokeTestParserStr(self, parser: _ev.ParserFSM) -> None:
        assert isinstance(str(parser), str)

    @pytest.mark.parametrize("state", [_ev.NoopState, _ev.HeaderState, _ev.BodyState])
    def testSmokeTestStateStr(
        self, parser: _ev.ParserFSM, state: type[_ev.AbstractState]
    ) -> None:
        assert isinstance(str(state(parser)), str)

    def testParseNotAHeader(
        self, parser: _ev.ParserFSM, results: list[str | None]
    ) -> None:
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
    def testGetClassValue(self, eclass: _ev.EClass) -> None:
        content = "{}: xxx\n".format(eclass.value)
        assert _ev.Elog.getClass(content) is eclass

    @pytest.mark.parametrize("eclass", _ev.EClass)
    def testGetClassWrongCaseDoesNotMatch(self, eclass: _ev.EClass) -> None:
        content = "QA: xxx\n{}: xxx".format(eclass.value.lower())
        assert _ev.Elog.getClass(content) is _ev.EClass.QA

    def testGetClassDefaultsToLog(self) -> None:
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
    def testGetClassMisc(self, content: str, eclass: _ev.EClass) -> None:
        assert _ev.Elog.getClass(content) is eclass


class TestElogClass:
    @pytest.fixture(params=_ev.EClass)
    def eclass(self, request: pytest.FixtureRequest) -> _ev.EClass:
        return request.param

    @pytest.fixture
    def elogFile(self, eclass: _ev.EClass) -> FakeElog:
        return FakeElog(
            randomElogFileName(), randomElogContent(eclass, _fuzz.randomString(10))
        )

    @pytest.fixture
    def elogFullPath(self, elogPath: Path, elogFile: FakeElog) -> Path:
        return elogPath / elogFile.fileName

    @pytest.fixture
    def elogContents(self, elogFile: FakeElog) -> str:
        return elogFile.content

    @pytest.fixture
    def elogClassInstance(
        self, elogFullPath: Path, elogFile: FakeElog, fs: Any
    ) -> _ev.Elog:
        fs.create_file(elogFullPath, contents=elogFile.content)
        return _ev.Elog.fromFilename(elogFullPath)

    def testFileName(self, elogClassInstance: _ev.Elog, elogFullPath: Path) -> None:
        assert elogClassInstance.filename == str(elogFullPath)

    def testContents(self, elogClassInstance: _ev.Elog, elogContents: str) -> None:
        assert elogClassInstance.contents == elogContents

    def testEClass(
        self, elogClassInstance: _ev.Elog, eclass: _ev.EClass, elogFile: FakeElog
    ) -> None:
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
    def testHtml(
        self, elogText: str, elogHtml: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(_ev.Elog, "file", closing(io.StringIO(elogText)))
        elog = _ev.Elog("", "", "", time.gmtime(0), _ev.EClass.Log)
        assert elog.html == elogHtml


@pytest.mark.usefixtures("elogsToFS")
class TestUI:
    @pytest.fixture
    def config(self, elogPath: Path) -> Any:
        from collections import namedtuple

        config_ = namedtuple("Config", "elogpath")
        config_.elogpath = elogPath  # type: ignore
        return config_

    @pytest.fixture
    def elogviewer(
        self, config: Any, qtbot: Any, qtmodeltester: Any
    ) -> Iterator[_ev.Elogviewer]:
        elogviewer = _ev.Elogviewer(config)
        elogviewer.populate()
        qtbot.addWidget(elogviewer)
        yield elogviewer
        qtmodeltester.check(elogviewer.model)
        qtbot.keyClick(
            elogviewer.tableView, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier
        )
        qtbot.mouseClick(elogviewer.markUnreadButton, Qt.MouseButton.LeftButton)
        qtbot.mouseClick(elogviewer.toggleImportantButton, Qt.MouseButton.LeftButton)
        if elogviewer.importantCount():
            qtbot.mouseClick(
                elogviewer.toggleImportantButton, Qt.MouseButton.LeftButton
            )

    def testHasElogs(
        self, elogviewer: _ev.Elogviewer, elogPath: Path, elogCount: int
    ) -> None:
        assert _count(elogPath.glob("*.log")) == elogCount
        assert elogviewer.elogCount() == elogCount

    def testOneRead(self, elogviewer: _ev.Elogviewer, qtbot: Any) -> None:
        assert elogviewer.readCount() == 0

        qtbot.keyClick(elogviewer.tableView, Qt.Key.Key_Up)
        qtbot.mouseClick(elogviewer.markReadButton, Qt.MouseButton.LeftButton)

        assert elogviewer.readCount() == 1

    def testAllRead(
        self, elogviewer: _ev.Elogviewer, elogCount: int, qtbot: Any
    ) -> None:
        assert elogviewer.readCount() == 0

        qtbot.keyClick(
            elogviewer.tableView, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier
        )
        qtbot.mouseClick(elogviewer.markReadButton, Qt.MouseButton.LeftButton)
        assert elogviewer.readCount() == elogCount

    def testAllUnread(
        self, elogviewer: _ev.Elogviewer, elogCount: int, qtbot: Any
    ) -> None:
        qtbot.keyClick(elogviewer.tableView, Qt.Key.Key_Up)
        qtbot.keyClick(
            elogviewer.tableView, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier
        )
        qtbot.mouseClick(elogviewer.markReadButton, Qt.MouseButton.LeftButton)
        assert elogviewer.readCount() == elogCount

        qtbot.keyClick(
            elogviewer.tableView, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier
        )
        qtbot.mouseClick(elogviewer.markUnreadButton, Qt.MouseButton.LeftButton)
        assert elogviewer.readCount() == 0

    def testOneImportant(self, elogviewer: _ev.Elogviewer, qtbot: Any) -> None:
        assert elogviewer.importantCount() == 0

        qtbot.keyClick(elogviewer.tableView, Qt.Key.Key_Up)
        qtbot.mouseClick(elogviewer.toggleImportantButton, Qt.MouseButton.LeftButton)

        assert elogviewer.importantCount() == 1

    def testAllImportant(
        self, elogviewer: _ev.Elogviewer, elogCount: int, qtbot: Any
    ) -> None:
        assert elogviewer.importantCount() == 0

        qtbot.keyClick(
            elogviewer.tableView, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier
        )
        qtbot.mouseClick(elogviewer.toggleImportantButton, Qt.MouseButton.LeftButton)

        assert elogviewer.importantCount() == elogCount

    @pytest.mark.skip
    def testRefreshButton(
        self, elogviewer: _ev.Elogviewer, elogPath: Path, elogCount: int, qtbot: Any
    ) -> None:
        qtbot.keyClick(
            elogviewer.tableView, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier
        )
        qtbot.mouseClick(elogviewer.deleteButton, Qt.MouseButton.LeftButton)

        qtbot.mouseClick(elogviewer.refreshButton, Qt.MouseButton.LeftButton)

        assert _count(elogPath.glob("*.log")) == elogCount
        assert elogviewer.elogCount() == elogCount

    def testDeleteOne(
        self, elogviewer: _ev.Elogviewer, elogPath: Path, elogCount: int, qtbot: Any
    ) -> None:
        qtbot.keyClick(elogviewer.tableView, Qt.Key.Key_Up)
        count = elogviewer.elogCount()
        assert count == elogCount

        qtbot.mouseClick(elogviewer.deleteButton, Qt.MouseButton.LeftButton)

        assert count == elogCount
        assert elogviewer.elogCount() == count - 1
        assert elogviewer.elogCount() == _count(elogPath.glob("*.log"))

    def testDeleteTwo(
        self, elogviewer: _ev.Elogviewer, elogPath: Path, elogCount: int, qtbot: Any
    ) -> None:
        qtbot.keyClick(elogviewer.tableView, Qt.Key.Key_Up)
        count = elogviewer.elogCount()
        assert count == elogCount

        qtbot.mouseClick(elogviewer.deleteButton, Qt.MouseButton.LeftButton)
        qtbot.mouseClick(elogviewer.deleteButton, Qt.MouseButton.LeftButton)

        assert count == elogCount
        assert elogviewer.elogCount() == count - 2
        assert elogviewer.elogCount() == _count(elogPath.glob("*.log"))

    def testDeleteAll(
        self, elogviewer: _ev.Elogviewer, elogPath: Path, elogCount: int, qtbot: Any
    ) -> None:
        assert elogviewer.elogCount() == elogCount

        qtbot.keyClick(
            elogviewer.tableView, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier
        )
        qtbot.mouseClick(elogviewer.deleteButton, Qt.MouseButton.LeftButton)

        assert elogviewer.elogCount() == _count(elogPath.glob("*.log")) == 0

    def testDeleteAllPlusOne(
        self, elogviewer: _ev.Elogviewer, elogPath: Path, elogCount: int, qtbot: Any
    ) -> None:
        assert elogviewer.elogCount() == elogCount

        qtbot.keyClick(
            elogviewer.tableView, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier
        )
        qtbot.mouseClick(elogviewer.deleteButton, Qt.MouseButton.LeftButton)
        assert _count(elogPath.glob("*.log")) == 0

        qtbot.mouseClick(elogviewer.deleteButton, Qt.MouseButton.LeftButton)

        assert elogviewer.elogCount() == _count(elogPath.glob("*.log"))

    def testDecreaseCountOnLeavingRow(
        self, elogviewer: _ev.Elogviewer, qtbot: Any
    ) -> None:
        readCount = elogviewer.readCount()
        assert readCount == 0

        qtbot.keyClick(elogviewer.tableView, Qt.Key.Key_Up)
        qtbot.keyClick(elogviewer.tableView, Qt.Key.Key_Down)

        assert elogviewer.readCount() == readCount + 1
