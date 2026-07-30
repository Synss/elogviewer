import pytest
from archunitpython import assert_passes, project_files, project_layers
from archunitpython.common.types import Pattern

MODEL_FILES = (
    "src/elogviewer/eclass.py",
    "src/elogviewer/elog.py",
    "src/elogviewer/model.py",
    "src/elogviewer/parser.py",
)


def test_no_circular_dependencies():
    rule = project_files("src/").in_folder("src/**").should().have_no_cycles()
    assert_passes(rule)


@pytest.mark.parametrize("path", MODEL_FILES)
def test_model_is_qt_free(path: Pattern):
    rule = (
        project_files("src/")
        .in_path(path)
        .should_not()
        .depend_on_external_modules()
        .matching("PyQt*")
    )
    assert_passes(rule)


def test_mvc_layers_only_depend_downwards():
    architecture = project_layers("src/")
    for path in MODEL_FILES:
        architecture.layer("model").defined_by(path)
    architecture.layer("uimodel").defined_by("src/elogviewer/uimodel.py")
    architecture.layer("controller").defined_by("src/elogviewer/uicontroller.py")
    architecture.layer("view").defined_by("src/elogviewer/uiview.py")
    rule = (
        architecture.where_layer("model")
        .may_only_depend_on_layers()
        .where_layer("uimodel")
        .may_only_depend_on_layers("model")
        .where_layer("controller")
        .may_only_depend_on_layers("model", "uimodel")
        .where_layer("view")
        .may_only_depend_on_layers("model", "uimodel", "controller")
    )
    assert_passes(rule)
