# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import abc
import weakref
from typing import Protocol, TypeAlias, override

from .eclass import EClass
from .elog import Elog

RGB: TypeAlias = tuple[int, int, int]


class ColorStrategy(Protocol):
    def __call__(self, /, eclass: EClass) -> RGB: ...


class AbstractState(abc.ABC):
    def __init__(self, context: ParserFSM) -> None:
        self.context = weakref.proxy(context)

    @override
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
    @override
    def enter(self) -> None:
        pass

    @override
    def exit(self) -> None:
        pass

    @override
    def parse(self, line: str) -> str:
        return line


class HeaderState(AbstractState):
    @override
    def enter(self) -> str:
        return "<h3>"

    @override
    def exit(self) -> str:
        return "</h3>"

    @override
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
        url=r"http://packages.gentoo.org/packages/\1",
        text=r"\1-\2",
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

    @override
    def enter(self) -> str:
        color = "".join(
            format(_, "02x") for _ in self.context.colorStrategy(self.context.eclass)
        )
        return f'<p style="color: #{color}">'

    @override
    def exit(self) -> str:
        return "</p>"

    @override
    def parse(self, line: str) -> str:
        line = self._parse_ansi_colors(line)
        line = self._parse_link(line)
        line = self._parse_bug(line)
        line = self._parse_pkg(line)
        return f"{line} <br />"


class ParserFSM:
    def __init__(
        self,
        results: list[str | None],
        *,
        colorStrategy: ColorStrategy,
    ) -> None:
        self.eclass = EClass.Log
        self.colorStrategy = colorStrategy
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

    @override
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
