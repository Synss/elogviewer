from archunitpython import project_files, assert_passes
from archunitpython.common.types import Pattern

import pytest


def test_no_circular_dependencies():
    rule = project_files("src/").in_folder("src/**").should().have_no_cycles()
    assert_passes(rule)


@pytest.mark.parametrize(
    "path",
    [
        "src/elogviewer/eclass.py",
        "src/elogviewer/elog.py",
        "src/elogviewer/model.py",
        "src/elogviewer/parser.py",
    ],
)
def test_model_is_qt_free(path: Pattern):
    rule = (
        project_files("src/")
        .in_path(path)
        .should_not()
        .depend_on_external_modules()
        .matching("PyQt*")
    )
    assert_passes(rule)
