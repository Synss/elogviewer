import sys
import os
from glob import glob
import unittest
from unittest import mock
from collections import namedtuple
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtTest import QTest

Qt = QtCore.Qt
import elogviewer

Column = elogviewer.Column
elogviewer.logger.setLevel(100)  # silence logging
from elogviewer import _file, _itemFromIndex, _html


config = namedtuple("Config", "elogpath")
config.elogpath = "data"

TEST_SET_SIZE = 5


class TestQtBase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.app = QtWidgets.QApplication([])


class TestRepr(unittest.TestCase):
    def assert_well_formatted_repr(self, obj):
        self.assertIsInstance(eval(repr(obj)), type(obj))


class TestDelegateRepr(TestQtBase, TestRepr):
    def test_TextToHtmlDelegate(self):
        self.assert_well_formatted_repr(elogviewer.TextToHtmlDelegate())

    def test_ButtonDelegate(self):
        button = mock.Mock()
        button.__repr__ = mock.Mock()
        button.__repr__.return_value = "QtWidgets.QPushButton()"
        self.assert_well_formatted_repr(elogviewer.ButtonDelegate(button))


class TestBase(TestQtBase):
    def setUp(self):
        super().setUp()
        self.reset_test_set()
        self.elogviewer = elogviewer.Elogviewer(config)
        self.elogviewer.populate()

    def tearDown(self):
        super().tearDown()
        assert self.elogviewer.close()
        del self.elogviewer

    @property
    def elogs(self):
        return glob(os.path.join(config.elogpath, "*.log"))

    @property
    def htmls(self):
        return [".".join((os.path.splitext(elog)[0], "html")) for elog in self.elogs]

    def delete_test_set(self):
        assert os.getcwd() == os.path.dirname(elogviewer.__file__)
        os.system("rm -r %s" % config.elogpath)

    def reset_test_set(self):
        os.system("git checkout -- %s" % config.elogpath)

    def assert_elog_files_exist(self):
        self.assertEqual(len(self.elogs), TEST_SET_SIZE)

    def assert_elog_files_deleted(self):
        self.assertEqual(len(self.elogs), 0)

    def assert_html_files_exist(self):
        self.assertEqual(len(self.htmls), TEST_SET_SIZE)

    def assert_html_files_deleted(self):
        self.assertEqual(len(self.htmls), 0)


class TestEnvironment(TestBase):
    def setUp(self):
        super().setUp()
        self.maxDiff = None
        for elog, html in zip(self.elogs, self.htmls):
            if not os.path.isfile(html):
                with open(html, "w") as html_file:
                    html_file.writelines(_html(elog))

    def test_delete_test_set(self):
        self.delete_test_set()
        self.assert_elog_files_deleted()
        self.assert_html_files_deleted()

    def test_reset_test_set(self):
        self.assert_elog_files_exist()
        self.assert_html_files_exist()

    def test_elog_loaded(self):
        self.assert_elog_files_exist()
        self.assertEqual(self.elogviewer.elogCount(), TEST_SET_SIZE)

    def test_html_parser(self):
        for elog, html in zip(self.elogs, self.htmls):
            with open(html, "r") as html_file:
                self.assertMultiLineEqual(_html(elog), "".join(html_file.readlines()))

    def test_unsupported_format(self):
        with _file(self.htmls[0]) as elogfile:
            content = b"".join(elogfile.readlines())
        self.assertRegex(content, b"ERROR:")


class TestGui(TestBase):
    def setUp(self):
        super().setUp()
        self.unset_important_flag()
        self.unset_read_flag()
        self.select_first()

    def _button(self, name):
        action = getattr(self.elogviewer, "%sAction" % name)
        return self.elogviewer.toolBar.widgetForAction(action)

    @property
    def refreshButton(self):
        return self._button("refresh")

    @property
    def markReadButton(self):
        return self._button("markRead")

    @property
    def markUnreadButton(self):
        return self._button("markUnread")

    @property
    def toggleImportantButton(self):
        return self._button("markImportant")

    @property
    def deleteButton(self):
        return self._button("delete")

    @property
    def aboutButton(self):
        return self._button("about")

    def select_first(self):
        self.elogviewer.tableView.selectionModel().clear()
        self.elogviewer.tableView.selectRow(0)

    def select_all(self):
        QTest.keyClick(self.elogviewer.tableView, Qt.Key_A, Qt.ControlModifier)

    def unset_important_flag(self):
        self.select_all()
        for index in self.elogviewer.tableView.selectionModel().selectedRows(
            Column.ImportantState
        ):
            _itemFromIndex(index).setImportantState(Qt.Unchecked)

    def unset_read_flag(self):
        self.select_all()
        for index in self.elogviewer.tableView.selectionModel().selectedRows(
            Column.ReadState
        ):
            _itemFromIndex(index).setReadState(Qt.Unchecked)

    def assert_elog_count_consistent(self):
        self.assertEqual(self.elogviewer.elogCount(), len(self.elogs))

    def assert_elog_count_equal(self, value):
        self.assertEqual(self.elogviewer.elogCount(), value)

    def assert_read_count_equal(self, value):
        self.assertEqual(self.elogviewer.readCount(), value)

    def assert_important_count_equal(self, value):
        self.assertEqual(self.elogviewer.importantCount(), value)


class TestGuiButtons(TestGui):
    def test_delete_one(self):
        self.select_first()

        QTest.mouseClick(self.deleteButton, Qt.LeftButton)

        self.assert_elog_count_equal(TEST_SET_SIZE - 1)
        self.assert_elog_count_consistent()

    def test_delete_two(self):
        self.select_first()
        self.assert_elog_count_equal(TEST_SET_SIZE)

        QTest.mouseClick(self.deleteButton, Qt.LeftButton)
        QTest.mouseClick(self.deleteButton, Qt.LeftButton)

        self.assert_elog_count_equal(TEST_SET_SIZE - 2)
        self.assert_elog_count_consistent()

    def test_delete_all(self):
        self.select_all()

        QTest.mouseClick(self.deleteButton, Qt.LeftButton)

        self.assert_elog_files_deleted()
        self.assert_elog_count_consistent()

    def test_delete_all_plus_one(self):
        self.select_all()

        QTest.mouseClick(self.deleteButton, Qt.LeftButton)
        QTest.mouseClick(self.deleteButton, Qt.LeftButton)

        self.assert_elog_files_deleted()
        self.assert_elog_count_consistent()

    def test_refresh_button(self):
        self.select_all()
        QTest.mouseClick(self.deleteButton, Qt.LeftButton)
        self.reset_test_set()

        QTest.mouseClick(self.refreshButton, Qt.LeftButton)

        self.assert_elog_files_exist()
        self.assert_elog_count_consistent()

    def test_one_read(self):
        QTest.mouseClick(self.markReadButton, Qt.LeftButton)
        self.assert_read_count_equal(1)

    def test_all_read(self):
        self.select_all()
        QTest.mouseClick(self.markReadButton, Qt.LeftButton)
        self.assert_read_count_equal(TEST_SET_SIZE)

    def test_all_unread(self):
        QTest.mouseClick(self.markUnreadButton, Qt.LeftButton)
        self.assert_read_count_equal(0)

    def test_one_important(self):
        QTest.mouseClick(self.toggleImportantButton, Qt.LeftButton)
        self.assert_important_count_equal(1)

    def test_all_important(self):
        self.select_all()
        QTest.mouseClick(self.toggleImportantButton, Qt.LeftButton)
        self.assert_important_count_equal(TEST_SET_SIZE)


class TestReadCounter(TestGui):
    def test_decrease_count_on_leaving_row(self):
        self.elogviewer.tableView.selectRow(0)
        self.elogviewer.tableView.selectRow(1)
        self.elogviewer.tableView.selectRow(2)

        self.assert_read_count_equal(TEST_SET_SIZE - 2)


if __name__ == "__main__":
    unittest.main()
