import random
import string
import time
from functools import partial


def randomString(length, choice=random.choice, charset=string.ascii_lowercase):
    return "".join(choice(charset) for _ in range(length))


def randomParagraph(length, stringLength):
    return " ".join(randomString(stringLength) for _ in range(length))


def randomText(length, paragraphLength, stringLength):
    return "\n\n".join(
        randomParagraph(paragraphLength, stringLength) for _ in range(length)
    )


def randomSection(header, content):
    return "\n".join(header, content)


def randomTime(begin, end):
    return time.gmtime(random.randint(int(time.mktime(begin)), int(time.mktime(end))))


def randomElogContent(eclass):
    return "\n".join(
        (
            "{}: {}".format(eclass.name[1:].upper(), randomString(10)),
            randomText(5, 10, 10),
        )
    )


def randomElogFileName():
    now = time.gmtime()
    return (
        ":".join(
            (
                "{}-{}".format(randomString(3), randomString(10)),
                "{}-{}.{}.{}".format(
                    randomString(10),
                    random.randint(0, 9),
                    random.randint(0, 9),
                    random.randint(0, 9),
                ),
                time.strftime(
                    "%Y%m%d-%H%M%S", randomTime((now.tm_year - 1, *now[1:]), now)
                ),
            )
        )
        + ".log"
    )
