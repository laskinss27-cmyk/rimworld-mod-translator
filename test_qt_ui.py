import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from rimworld_translator_qt import MainWindow, STYLE
    HAS_QT = True
except ImportError:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 is only required for the Qt edition")
class QtInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings_dir = tempfile.TemporaryDirectory()
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, cls.settings_dir.name)
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(STYLE)

    def test_window_builds_and_switches_language(self):
        window = MainWindow()
        window.language_code = "ru"
        window._apply_language()
        self.assertIn("Экспортировать", window.export_button.text())
        self.assertEqual(window.edition_badge.text(), "QT EDITION")

        window.toggle_language()

        self.assertEqual(window.language_code, "en")
        self.assertIn("Export", window.export_button.text())
        self.assertIn("Build", window.build_button.text())
        window.close()

    @classmethod
    def tearDownClass(cls):
        cls.settings_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
