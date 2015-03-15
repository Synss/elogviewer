import sys
import os
from glob import glob
import unittest
from collections import namedtuple
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtTest import QTest
Qt = QtCore.Qt
import elogviewer as e
e.logger.setLevel(100)  # silence logging


class TestBase(unittest.TestCase):

    def setUp(self):
        self.reset_test_set()

    def reset_test_set(self):
        self.config = namedtuple("Config", "elogpath")
        self.config.elogpath = "data"
        self.assertEqual(os.getcwd(), os.path.dirname(e.__file__))
        os.system("rm -r %s" % self.config.elogpath)
        os.system("git checkout -- %s" % self.config.elogpath)

    @property
    def elogs(self):
        return glob(os.path.join(self.config.elogpath, "*.log"))

    @property
    def htmls(self):
        return [".".join((os.path.splitext(elog)[0], "html"))
                for elog in self.elogs]


class TestElogviewer(TestBase):

    def setUp(self):
        super().setUp()
        self.maxDiff = None
        for elog, html in zip(self.elogs, self.htmls):
            if not os.path.isfile(html):
                with open(html, "w") as html_file:
                    html_file.writelines(
                        e.TextToHtmlDelegate.toHtml(e.Elog(elog)))

    def test_html_parser(self):
        for elog, html in zip(self.elogs, self.htmls):
            with open(html, "r") as html_file:
                self.assertMultiLineEqual(
                    e.TextToHtmlDelegate.toHtml(e.Elog(elog)),
                    "".join(html_file.readlines()))

    def test_unsupported_format(self):
        with e.Elog(self.htmls[0]).file as elogfile:
            content = elogfile.readlines()
        self.assertNotEqual(content, [])
        self.assertIsInstance(b"".join(content), bytes)


class TestGui(TestBase):

    def setUp(self):
        super().setUp()

        def button(name):
            action = getattr(self.elogviewer, "%sAction" % name)
            button = self.elogviewer.toolBar.widgetForAction(action)
            return button

        self.app = QtWidgets.QApplication(sys.argv)
        self.elogviewer = e.Elogviewer(self.config)
        self.refreshButton = button("refresh")
        self.markReadButton = button("markRead")
        self.markUnreadButton = button("markUnread")
        self.toggleImportantButton = button("markImportant")
        self.deleteButton = button("delete")
        self.aboutAction = button("about")

    def select_all(self):
        QTest.keyClick(self.elogviewer.tableView, Qt.Key_A, Qt.ControlModifier)

    def reset_select_all(self):
        self.elogviewer.tableView.selectionModel().clear()
        self.elogviewer.tableView.selectRow(0)

    def test_elog_count(self):
        elogCount = len(self.elogs)
        self.assertNotEqual(elogCount, 0)
        self.assertNotEqual(self.elogviewer.elogCount(), 0)
        self.assertEqual(self.elogviewer.elogCount(), elogCount)

    def test_delete_and_refresh_buttons(self):
        # sanity check
        self.reset_test_set()
        elogCount = self.elogviewer.elogCount()
        self.assertNotEqual(elogCount, 0)
        # delete one
        self.elogviewer.tableView.selectRow(0)
        QTest.mouseClick(self.deleteButton, Qt.LeftButton)
        self.assertEqual(self.elogviewer.elogCount(), elogCount - 1)
        # delete all
        self.select_all()
        QTest.mouseClick(self.deleteButton, Qt.LeftButton)
        self.assertEqual(self.elogviewer.elogCount(), 0)
        self.assertEqual(self.elogviewer.currentRow(), -1)
        self.assertEqual(self.elogviewer.unreadCount(), 0)
        self.assertEqual(self.elogviewer.readCount(), 0)
        self.assertEqual(len(self.elogs), 0)
        # undelete and check refresh
        self.reset_test_set()
        self.assertNotEqual(len(self.elogs), 0)
        self.assertEqual(self.elogviewer.elogCount(), 0)
        QTest.mouseClick(self.refreshButton, Qt.LeftButton)
        self.assertEqual(self.elogviewer.elogCount(), len(self.elogs))
        self.assertEqual(self.elogviewer.elogCount(), elogCount)

    def test_mark_read_unread_buttons(self):
        # sanity check
        elogviewer = self.elogviewer
        self.assertNotEqual(elogviewer.elogCount(), 0)
        self.select_all()
        # check unread
        QTest.mouseClick(self.markUnreadButton, Qt.LeftButton)
        self.assertEqual(elogviewer.unreadCount(), elogviewer.elogCount())
        self.assertEqual(elogviewer.unreadCount(), len(self.elogs))
        self.assertNotEqual(elogviewer.unreadCount(), elogviewer.readCount())
        self.assertEqual(len(e.Elog._readFlag), elogviewer.readCount())
        # check read
        QTest.mouseClick(self.markReadButton, Qt.LeftButton)
        self.assertEqual(elogviewer.readCount(), elogviewer.elogCount())
        self.assertNotEqual(elogviewer.unreadCount(), elogviewer.readCount())
        self.assertEqual(elogviewer.readCount(), len(self.elogs))
        self.assertEqual(len(e.Elog._readFlag), elogviewer.readCount())
        # reset selection
        self.reset_select_all()

    def test_important_button(self):
        def reset_important_flag():
            self.select_all()
            for index in elogviewer.tableView.selectionModel().selectedRows(
                    e.Column.ImportantState):
                elogviewer.setImportantState(index, Qt.Unchecked)
        # sanity check
        elogviewer = self.elogviewer
        self.assertNotEqual(elogviewer.elogCount(), 0)
        # initialize: all not important
        reset_important_flag()
        self.assertEqual(elogviewer.importantCount(), 0)
        # test one important
        reset_important_flag()
        self.reset_select_all()
        QTest.mouseClick(self.toggleImportantButton, Qt.LeftButton)
        self.assertEqual(elogviewer.importantCount(), 1)
        # test all important
        reset_important_flag()
        self.select_all()
        QTest.mouseClick(self.toggleImportantButton, Qt.LeftButton)
        self.assertEqual(elogviewer.importantCount(), elogviewer.elogCount())
        # test toggle important
        QTest.mouseClick(self.toggleImportantButton, Qt.LeftButton)
        self.assertEqual(elogviewer.importantCount(), 0)
        # reset selection
        reset_important_flag()
        self.reset_select_all()


if __name__ == "__main__":
    unittest.main()
