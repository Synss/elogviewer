import random
import string
import time


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
