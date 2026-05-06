# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import bz2
import gzip
import io
import logging
import re
import time
from contextlib import AbstractContextManager, closing
from dataclasses import dataclass
from pathlib import Path
from typing import IO, final

from .eclass import EClass

_LOGGER = logging.getLogger("elogviewer")


def _open(filename: Path) -> AbstractContextManager[IO[str]]:
    ext = filename.suffix
    try:
        return {".gz": gzip.open, ".bz2": bz2.open, ".log": open}[ext](
            filename,
            "rt",
        )
    except KeyError:
        _LOGGER.error("%s: unsupported format", filename)
        return closing(
            io.StringIO(
                """
                <!-- set eclass: ERROR: -->
                <h3>Unsupported format</h3>
                The selected elog is in an unsupported format.
                """,
            ),
        )
    except FileNotFoundError:
        _LOGGER.error("%s: file not found", filename)
        return closing(
            io.StringIO(
                """
                <!-- set eclass: ERROR: -->
                <h3>File not found</h3>
                The selected elog could does not exist on the filesystem.
                """,
            ),
        )
    except OSError:
        _LOGGER.error("%s: could not open file", filename)
        return closing(
            io.StringIO(
                """
                <!-- set eclass: ERROR: -->
                <h3>File does not open</h3>
                The selected elog could not be opened.
                """,
            ),
        )


@final
@dataclass(frozen=True)
class Elog:
    filename: Path
    category: str
    package: str
    date: time.struct_time
    eclass: EClass
    contents: str

    HeaderPattern = re.compile(
        r"({}):\s+(\S+)".format("|".join(_.value for _ in EClass)),
    )
    AnsiColorPattern = re.compile(r"\x1b\[[0-9;]+m")
    LinkPattern = re.compile(r"((https?|ftp)://\S+)", re.IGNORECASE)
    BugPattern = re.compile(r"([bB]ug)\s+#([0-9]+)", re.IGNORECASE)
    PackagePattern = re.compile(
        r"([a-z0-9]+-[a-z0-9]+/[a-z0-9]+)-([0-9.]+)",
        re.IGNORECASE,
    )

    @classmethod
    def fromFilename(cls, filename: Path) -> Elog:
        _LOGGER.debug(filename)
        try:
            category, package, rest = filename.name.split(":")
        except ValueError:
            category = filename.parent.name
            package, rest = filename.name.split(":")
        date = time.strptime(rest.split(".")[0], "%Y%m%d-%H%M%S")
        with _open(filename) as f:
            contents = f.read()
        return cls(filename, category, package, date, cls.getClass(contents), contents)

    @classmethod
    def getClass(cls, elogBody: str) -> EClass:
        # Get the highest elog class. Adapted from Luca Marturana's elogv.
        eClasses = frozenset(_[0] for _ in cls.HeaderPattern.findall(elogBody))
        for eClass in EClass:
            if eClass.value in eClasses:
                return eClass
        _LOGGER.error("elog has no identifiable eclass")
        return EClass.Log
