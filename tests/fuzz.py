from __future__ import annotations

import random
import string
import time
from collections.abc import Callable


def randomString(
    length: int,
    choice: Callable[[str], str] = random.choice,
    charset: str = string.ascii_lowercase,
) -> str:
    return "".join(choice(charset) for _ in range(length))


def randomParagraph(length: int, stringLength: int) -> str:
    return " ".join(randomString(stringLength) for _ in range(length))


def randomText(length: int, paragraphLength: int, stringLength: int) -> str:
    return "\n\n".join(
        randomParagraph(paragraphLength, stringLength) for _ in range(length)
    )


def randomSection(header: str, content: str) -> str:
    return "\n".join([header, content])


def randomTime(
    begin: time.struct_time | tuple[int, int, int, int, int, int, int, int, int],
    end: time.struct_time | tuple[int, int, int, int, int, int, int, int, int],
) -> time.struct_time:
    return time.gmtime(random.randint(int(time.mktime(begin)), int(time.mktime(end))))
