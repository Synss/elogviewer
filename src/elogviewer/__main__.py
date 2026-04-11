# SPDX-License-Identifier: GPL-2.0-only

import argparse
import logging
import sys
from pathlib import Path

from PyQt6 import QtGui, QtWidgets

from elogviewer.uiview import Elogviewer

try:
    import portage  # type: ignore[import-not-found]
except ImportError:
    portage = None  # type: ignore


_LOGGER = logging.getLogger("elogviewer")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-p",
        "--elogpath",
        help="path to the elog directory",
        default="",
    )
    parser.add_argument(
        "--log",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="WARNING",
        help="set logging level",
    )

    config = parser.parse_args()

    logging.basicConfig()
    _LOGGER.setLevel(getattr(logging, config.log))

    _LOGGER.debug("running on python %s", sys.version)
    if portage and not config.elogpath:
        logdir = portage.settings["PORT_LOGDIR"]  # type: ignore
        if not logdir:
            logdir = (
                Path(portage.settings["EPREFIX"] or "/")  # type: ignore
                / "var"
                / "log"
                / "portage"
            )
        config.elogpath = Path(logdir) / "elog"
    else:
        config.elogpath = Path(config.elogpath)

    _LOGGER.debug("elogpath is set to %r", config.elogpath)

    app = QtWidgets.QApplication(sys.argv)
    _fsPaths = [
        Path(p) for p in QtGui.QIcon.themeSearchPaths() if not p.startswith(":")
    ]
    _fallback = next(
        (
            theme
            for theme in ("breeze", "Adwaita", "gnome")
            if any((p / theme / "index.theme").exists() for p in _fsPaths)
        ),
        None,
    )
    if _fallback:
        QtGui.QIcon.setFallbackThemeName(_fallback)
    app.setWindowIcon(QtGui.QIcon.fromTheme("applications-system"))

    elogviewer = Elogviewer(config)
    elogviewer.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
