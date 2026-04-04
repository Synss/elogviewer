# SPDX-License-Identifier: GPL-2.0-only

import enum


class EClass(str, enum.Enum):
    Error = "ERROR"
    Warning = "WARN"
    Log = "LOG"
    Info = "INFO"
    QA = "QA"
