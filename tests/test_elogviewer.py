from __future__ import annotations

import io
import os
import random
import time
from collections.abc import Iterable, Iterator
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TypeAlias

import pytest
from pyfakefs.fake_filesystem_unittest import Patcher
from PyQt6.QtCore import Qt

from elogviewer.eclass import EClass
from elogviewer.elog import Elog
from elogviewer.parser import (
    AbstractState,
    BodyState,
    HeaderState,
    NoopState,
    ParserFSM,
)
from elogviewer.uiview import Elogviewer, eclassColor, makeHtml

from . import fuzz as _fuzz

QtBot: TypeAlias = Any
QtModelTester: TypeAlias = Any


class _FakeFilesystem(Protocol):
    def create_file(
        self,
        file_path: str | os.PathLike[str],
        contents: str = "",
    ) -> object: ...


def randomElogContent(eclass: EClass, stage: str) -> str:
    return "\n".join((f"{eclass.value}: {stage}", _fuzz.randomText(5, 10, 10)))


def randomElogFileName() -> str:
    now = time.gmtime()
    return (
        ":".join(
            (
                f"{_fuzz.randomString(3)}-{_fuzz.randomString(10)}",
                f"{_fuzz.randomString(10)}-{random.randint(0, 9)}.{random.randint(0, 9)}.{random.randint(0, 9)}",
                time.strftime(
                    "%Y%m%d-%H%M%S",
                    _fuzz.randomTime((now.tm_year - 1, *now[1:]), now),
                ),
            ),
        )
        + ".log"
    )


@dataclass(frozen=True)
class Config:
    elogpath: Path


@dataclass(frozen=True)
class FakeElog:
    fileName: str
    content: str


def _count(iterable: Iterable[object]) -> int:
    return sum(1 for _ in iterable)


@pytest.fixture
def elogPath() -> Iterator[Path]:
    with Patcher():
        yield Path("/var/log/portage/elog/")


class TestParserFSM:
    @pytest.fixture
    def parser(self) -> Iterator[ParserFSM]:
        with ParserFSM([], colorStrategy=eclassColor) as parser:
            yield parser

    def testSmokeTestParserStr(self, parser: ParserFSM) -> None:
        assert isinstance(str(parser), str)

    @pytest.mark.parametrize("state", [NoopState, HeaderState, BodyState])
    def testSmokeTestStateStr(
        self,
        parser: ParserFSM,
        state: type[AbstractState],
    ) -> None:
        assert isinstance(str(state(parser)), str)

    def testParseNotAHeader(self, parser: ParserFSM) -> None:
        # Gentoo Bug 721522
        for line in "LOG: xxx\nSection content".splitlines():
            # Initialize FSM
            parser.parse(line)
        assert type(parser.state) is BodyState

        # Looks like a header but is not.
        line = "ERROR: dev-python/sqlalchemy-migrate-0.13.0::gentoo failed (prepare phase):"
        parser.parse(line)

        assert type(parser.state) is BodyState


class TestElogClassUnit:
    @pytest.mark.parametrize("eclass", EClass)
    def testGetClassValue(self, eclass: EClass) -> None:
        content = f"{eclass.value}: xxx\n"
        assert Elog.getClass(content) is eclass

    @pytest.mark.parametrize("eclass", EClass)
    def testGetClassWrongCaseDoesNotMatch(self, eclass: EClass) -> None:
        content = f"QA: xxx\n{eclass.value.lower()}: xxx"
        assert Elog.getClass(content) is EClass.QA

    def testGetClassDefaultsToLog(self) -> None:
        content = "XXX: xxx\nXXX: xxx"
        assert Elog.getClass(content) is EClass.Log

    @pytest.mark.parametrize(
        "content, eclass",
        [
            ("LOG: xxx\nWARN: xxx\n", EClass.Warning),
            ("QA: xxx\nWARN: xxx\nERROR: xxx\n", EClass.Error),
            ("QA: xxx\nWARN: xxx\nError: xxx\n", EClass.Warning),
            ("QA: xxx\nINFO: xxx\nINFO: xxx", EClass.Info),
        ],
    )
    def testGetClassMisc(self, content: str, eclass: EClass) -> None:
        assert Elog.getClass(content) is eclass


class TestElogClass:
    @pytest.fixture(params=EClass)
    def eclass(self, request: pytest.FixtureRequest) -> EClass:
        return request.param

    @pytest.fixture
    def elogFile(self, eclass: EClass) -> FakeElog:
        return FakeElog(
            randomElogFileName(),
            randomElogContent(eclass, _fuzz.randomString(10)),
        )

    @pytest.fixture
    def elogClassInstance(
        self,
        elogPath: Path,
        elogFile: FakeElog,
        fs: _FakeFilesystem,
    ) -> Elog:
        path = elogPath / elogFile.fileName
        fs.create_file(path, contents=elogFile.content)
        return Elog.fromFilename(path)

    def testFileName(
        self,
        elogClassInstance: Elog,
        elogPath: Path,
        elogFile: FakeElog,
    ) -> None:
        assert elogClassInstance.filename == elogPath / elogFile.fileName

    def testContents(self, elogClassInstance: Elog, elogFile: FakeElog) -> None:
        assert elogClassInstance.contents == elogFile.content

    def testEClass(self, elogClassInstance: Elog, eclass: EClass) -> None:
        assert elogClassInstance.eclass is eclass

    @pytest.mark.parametrize(
        "elogText, elogHtml",
        [
            # Regular logs
            (
                "ERROR: error_stage\ntext",
                "<h3>\n"
                "Error:  error_stage\n\n"
                "</h3>\n"
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
        self,
        elogText: str,
        elogHtml: str,
    ) -> None:
        assert (
            makeHtml(closing(io.StringIO(elogText)), colorStrategy=eclassColor)
            == elogHtml
        )


class TestUI:
    @pytest.fixture(autouse=True)
    def elogsToFS(self, fs: _FakeFilesystem, elogPath: Path) -> None:
        for eclass in EClass:
            for _ in range(5):
                fakeElog = FakeElog(
                    randomElogFileName(),
                    randomElogContent(eclass, _fuzz.randomString(10)),
                )
                fs.create_file(elogPath / fakeElog.fileName, contents=fakeElog.content)

    @pytest.fixture
    def elogviewer(
        self,
        elogPath: Path,
        qtbot: QtBot,
        qtmodeltester: QtModelTester,
    ) -> Iterator[Elogviewer]:
        elogviewer = Elogviewer(Config(elogpath=elogPath))
        elogviewer.populate()
        qtbot.addWidget(elogviewer)
        qtbot.wait(150)  # consume QTimer.singleShot(100) while pyfakefs is active
        yield elogviewer
        qtmodeltester.check(elogviewer.model)
        qtbot.keyClick(
            elogviewer.tableView,
            Qt.Key.Key_A,
            Qt.KeyboardModifier.ControlModifier,
        )
        qtbot.mouseClick(elogviewer.markUnreadButton, Qt.MouseButton.LeftButton)
        qtbot.mouseClick(elogviewer.toggleImportantButton, Qt.MouseButton.LeftButton)
        if elogviewer.model.importantCount():
            qtbot.mouseClick(
                elogviewer.toggleImportantButton,
                Qt.MouseButton.LeftButton,
            )

    def testHasElogs(self, elogviewer: Elogviewer, elogPath: Path) -> None:
        assert elogviewer.model.elogCount() == _count(elogPath.glob("*.log")) > 0

    def testOneRead(self, elogviewer: Elogviewer, qtbot: QtBot) -> None:
        assert elogviewer.model.readCount() == 0

        qtbot.keyClick(elogviewer.tableView, Qt.Key.Key_Up)
        qtbot.mouseClick(elogviewer.markReadButton, Qt.MouseButton.LeftButton)

        assert elogviewer.model.readCount() == 1

    def testAllRead(self, elogviewer: Elogviewer, qtbot: QtBot) -> None:
        assert elogviewer.model.readCount() == 0

        qtbot.keyClick(
            elogviewer.tableView,
            Qt.Key.Key_A,
            Qt.KeyboardModifier.ControlModifier,
        )
        qtbot.mouseClick(elogviewer.markReadButton, Qt.MouseButton.LeftButton)
        assert elogviewer.model.readCount() == elogviewer.model.elogCount()

    def testAllUnread(self, elogviewer: Elogviewer, qtbot: QtBot) -> None:
        qtbot.keyClick(elogviewer.tableView, Qt.Key.Key_Up)
        qtbot.keyClick(
            elogviewer.tableView,
            Qt.Key.Key_A,
            Qt.KeyboardModifier.ControlModifier,
        )
        qtbot.mouseClick(elogviewer.markReadButton, Qt.MouseButton.LeftButton)
        assert elogviewer.model.readCount() == elogviewer.model.elogCount()

        qtbot.keyClick(
            elogviewer.tableView,
            Qt.Key.Key_A,
            Qt.KeyboardModifier.ControlModifier,
        )
        qtbot.mouseClick(elogviewer.markUnreadButton, Qt.MouseButton.LeftButton)
        assert elogviewer.model.readCount() == 0

    def testOneImportant(self, elogviewer: Elogviewer, qtbot: QtBot) -> None:
        assert elogviewer.model.importantCount() == 0

        qtbot.keyClick(elogviewer.tableView, Qt.Key.Key_Up)
        qtbot.mouseClick(elogviewer.toggleImportantButton, Qt.MouseButton.LeftButton)

        assert elogviewer.model.importantCount() == 1

    def testAllImportant(self, elogviewer: Elogviewer, qtbot: QtBot) -> None:
        assert elogviewer.model.importantCount() == 0

        qtbot.keyClick(
            elogviewer.tableView,
            Qt.Key.Key_A,
            Qt.KeyboardModifier.ControlModifier,
        )
        qtbot.mouseClick(elogviewer.toggleImportantButton, Qt.MouseButton.LeftButton)

        assert elogviewer.model.importantCount() == elogviewer.model.elogCount()

    @pytest.mark.skip
    def testRefreshButton(
        self,
        elogviewer: Elogviewer,
        elogPath: Path,
        qtbot: QtBot,
    ) -> None:
        count = elogviewer.model.elogCount()
        qtbot.keyClick(
            elogviewer.tableView,
            Qt.Key.Key_A,
            Qt.KeyboardModifier.ControlModifier,
        )
        qtbot.mouseClick(elogviewer.deleteButton, Qt.MouseButton.LeftButton)

        qtbot.mouseClick(elogviewer.refreshButton, Qt.MouseButton.LeftButton)

        assert _count(elogPath.glob("*.log")) == count
        assert elogviewer.model.elogCount() == count

    def testDeleteOne(
        self,
        elogviewer: Elogviewer,
        elogPath: Path,
        qtbot: QtBot,
    ) -> None:
        qtbot.keyClick(elogviewer.tableView, Qt.Key.Key_Up)
        count = elogviewer.model.elogCount()

        qtbot.mouseClick(elogviewer.deleteButton, Qt.MouseButton.LeftButton)

        assert elogviewer.model.elogCount() == count - 1
        assert elogviewer.model.elogCount() == _count(elogPath.glob("*.log"))

    def testDeleteTwo(
        self,
        elogviewer: Elogviewer,
        elogPath: Path,
        qtbot: QtBot,
    ) -> None:
        qtbot.keyClick(elogviewer.tableView, Qt.Key.Key_Up)
        count = elogviewer.model.elogCount()

        qtbot.mouseClick(elogviewer.deleteButton, Qt.MouseButton.LeftButton)
        qtbot.mouseClick(elogviewer.deleteButton, Qt.MouseButton.LeftButton)

        assert elogviewer.model.elogCount() == count - 2
        assert elogviewer.model.elogCount() == _count(elogPath.glob("*.log"))

    def testDeleteAll(
        self,
        elogviewer: Elogviewer,
        elogPath: Path,
        qtbot: QtBot,
    ) -> None:
        qtbot.keyClick(
            elogviewer.tableView,
            Qt.Key.Key_A,
            Qt.KeyboardModifier.ControlModifier,
        )
        qtbot.mouseClick(elogviewer.deleteButton, Qt.MouseButton.LeftButton)

        assert elogviewer.model.elogCount() == _count(elogPath.glob("*.log")) == 0

    def testDeleteAllPlusOne(
        self,
        elogviewer: Elogviewer,
        elogPath: Path,
        qtbot: QtBot,
    ) -> None:
        qtbot.keyClick(
            elogviewer.tableView,
            Qt.Key.Key_A,
            Qt.KeyboardModifier.ControlModifier,
        )
        qtbot.mouseClick(elogviewer.deleteButton, Qt.MouseButton.LeftButton)
        assert _count(elogPath.glob("*.log")) == 0

        qtbot.mouseClick(elogviewer.deleteButton, Qt.MouseButton.LeftButton)

        assert elogviewer.model.elogCount() == _count(elogPath.glob("*.log"))

    def testDecreaseCountOnLeavingRow(
        self,
        elogviewer: Elogviewer,
        qtbot: QtBot,
    ) -> None:
        readCount = elogviewer.model.readCount()
        assert readCount == 0

        qtbot.keyClick(elogviewer.tableView, Qt.Key.Key_Up)
        qtbot.keyClick(elogviewer.tableView, Qt.Key.Key_Down)

        assert elogviewer.model.readCount() == readCount + 1
