"""Modern PySide6 interface for RimWorld Mod Translator."""

import html
import os
import re
import sys
import traceback
from datetime import datetime

from PySide6.QtCore import QObject, QSettings, QThread, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from translator_service import (
    build_translation_package,
    default_translation_output,
    export_translations,
    import_into_original,
    inspect_mod,
    read_mod_metadata,
)


APP_VERSION = "5.0.0-beta.1"

TEXT = {
    "ru": {
        "title": "RimWorld Mod Translator",
        "subtitle": "Перевод модов без изменения оригинальных файлов",
        "source": "Исходный мод",
        "source_hint": "Перетащи сюда папку мода или выбери её вручную",
        "browse": "Выбрать",
        "open": "Открыть",
        "unknown_mod": "Мод ещё не выбран",
        "xml_files": "XML для перевода: {count}",
        "package": "Пакет: {package}",
        "versions": "Версии: {versions}",
        "extra_tags": "Дополнительные теги",
        "extra_hint": "Например: customLabel, flavorText",
        "export": "1  Экспортировать CSV",
        "build": "2  Собрать мод-перевод",
        "legacy": "Изменить оригинал",
        "log": "Журнал операций",
        "clear": "Очистить",
        "ready": "Готов к работе",
        "drop": "Отпусти папку мода здесь",
        "need_mod": "Сначала выбери существующую папку мода.",
        "choose_mod": "Выбери корневую папку RimWorld-мода",
        "save_csv": "Куда сохранить CSV",
        "choose_csv": "Выбери переведённый CSV",
        "done": "Готово",
        "error": "Ошибка",
        "exporting": "Сканирование и экспорт текста…",
        "building": "Создание отдельного мода-перевода…",
        "importing": "Изменение оригинальных XML…",
        "export_done": "CSV создан\n\nСтрок: {rows}\nНовых: {new}\nСохранено переводов: {merged}\n\n{output}",
        "build_done": "Мод-перевод создан\n\nСтрок: {entries}\nФайлов: {files}\nНе сопоставлено: {unmatched}\n\n{output}",
        "import_done": "Оригинальный мод обновлён\n\nСтрок: {applied}\nФайлов: {files}\nРезервная копия:\n{backup}",
        "legacy_title": "Опасный режим",
        "legacy_warning": "Этот режим изменяет XML оригинального мода. Перед записью будет создана резервная копия. Продолжить?",
        "build_title": "Параметры мода-перевода",
        "language": "Папка языка",
        "version": "Версия RimWorld",
        "csv": "Переведённый CSV",
        "destination": "Каталог результата",
        "choose": "Обзор…",
        "create": "Создать",
        "cancel": "Отмена",
        "invalid_build": "Укажи CSV, язык, версию вида 1.6 и каталог результата.",
        "inspect": "Чтение метаданных мода…",
        "modern": "QT EDITION",
        "about": "О версии",
        "about_text": "RimWorld Mod Translator Qt {version}\n\nИнтерфейс: PySide6 / Qt 6 (LGPLv3)\nИсходный код: github.com/laskinss27-cmyk/rimworld-mod-translator\n\nДвижок перевода распространяется по лицензии MIT.",
    },
    "en": {
        "title": "RimWorld Mod Translator",
        "subtitle": "Translate mods without modifying their original files",
        "source": "Source mod",
        "source_hint": "Drop a mod folder here or choose it manually",
        "browse": "Browse",
        "open": "Open",
        "unknown_mod": "No mod selected yet",
        "xml_files": "Translatable XML: {count}",
        "package": "Package: {package}",
        "versions": "Versions: {versions}",
        "extra_tags": "Additional tags",
        "extra_hint": "For example: customLabel, flavorText",
        "export": "1  Export CSV",
        "build": "2  Build translation mod",
        "legacy": "Edit original",
        "log": "Activity log",
        "clear": "Clear",
        "ready": "Ready",
        "drop": "Drop the mod folder here",
        "need_mod": "Choose an existing mod folder first.",
        "choose_mod": "Choose the RimWorld mod root",
        "save_csv": "Save CSV",
        "choose_csv": "Choose translated CSV",
        "done": "Done",
        "error": "Error",
        "exporting": "Scanning and exporting text…",
        "building": "Building a separate translation mod…",
        "importing": "Editing original XML files…",
        "export_done": "CSV created\n\nRows: {rows}\nNew: {new}\nPreserved: {merged}\n\n{output}",
        "build_done": "Translation mod created\n\nEntries: {entries}\nFiles: {files}\nUnmatched: {unmatched}\n\n{output}",
        "import_done": "Original mod updated\n\nEntries: {applied}\nFiles: {files}\nBackup:\n{backup}",
        "legacy_title": "Dangerous mode",
        "legacy_warning": "This mode edits the original mod XML. A backup will be created before writing. Continue?",
        "build_title": "Translation mod options",
        "language": "Language folder",
        "version": "RimWorld version",
        "csv": "Translated CSV",
        "destination": "Output directory",
        "choose": "Browse…",
        "create": "Create",
        "cancel": "Cancel",
        "invalid_build": "Choose a CSV, language, version such as 1.6, and output directory.",
        "inspect": "Reading mod metadata…",
        "modern": "QT EDITION",
        "about": "About",
        "about_text": "RimWorld Mod Translator Qt {version}\n\nInterface: PySide6 / Qt 6 (LGPLv3)\nSource: github.com/laskinss27-cmyk/rimworld-mod-translator\n\nThe translation engine is distributed under the MIT license.",
    },
}


STYLE = """
QWidget {
    background: #10131a;
    color: #e8eaf0;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 10pt;
}
QMainWindow { background: #10131a; }
QFrame#card, QFrame#dropCard {
    background: #171b24;
    border: 1px solid #282e3b;
    border-radius: 14px;
}
QFrame#dropCard[dragActive="true"] {
    background: #1b2437;
    border: 2px solid #7c6cff;
}
QLabel#title { font-size: 20pt; font-weight: 700; color: #ffffff; }
QLabel#subtitle, QLabel#muted { color: #9299aa; }
QLabel#section { color: #b8becb; font-size: 9pt; font-weight: 600; }
QLabel#badge {
    color: #bcb5ff;
    background: #272343;
    border: 1px solid #403975;
    border-radius: 9px;
    padding: 4px 9px;
    font-size: 8pt;
    font-weight: 700;
}
QLineEdit, QComboBox {
    background: #11151d;
    border: 1px solid #303746;
    border-radius: 9px;
    padding: 9px 11px;
    selection-background-color: #7464f5;
}
QLineEdit:focus, QComboBox:focus { border: 1px solid #8172ff; }
QPushButton {
    background: #222733;
    border: 1px solid #343b4a;
    border-radius: 9px;
    padding: 9px 14px;
    font-weight: 600;
}
QPushButton:hover { background: #2a3040; border-color: #535d72; }
QPushButton:pressed { background: #1c202a; }
QPushButton:disabled { color: #646b7a; background: #1a1e27; border-color: #272c37; }
QPushButton#primary {
    background: #7464f5;
    border-color: #7464f5;
    color: white;
    padding: 11px 17px;
}
QPushButton#primary:hover { background: #8476ff; border-color: #8476ff; }
QPushButton#secondary {
    background: #18352f;
    border-color: #286352;
    color: #a9ead7;
    padding: 11px 17px;
}
QPushButton#secondary:hover { background: #20463e; }
QPushButton#danger { color: #e7a2a7; }
QPushButton#language { padding: 6px 10px; color: #bbb4ff; }
QTextEdit {
    background: #0c0f15;
    border: 1px solid #272d39;
    border-radius: 10px;
    padding: 8px;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 9pt;
}
QProgressBar {
    background: #1b202a;
    border: 0;
    border-radius: 3px;
    height: 6px;
    text-align: center;
}
QProgressBar::chunk { background: #7464f5; border-radius: 3px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #353c4b; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #242a36; color: white; border: 1px solid #424a5d; }
"""


class TaskWorker(QObject):
    progress = Signal(int)
    log = Signal(str, str)
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, task):
        super().__init__()
        self.task = task

    @Slot()
    def run(self):
        try:
            result = self.task(self.progress.emit, self.log.emit)
            self.succeeded.emit(result)
        except Exception:
            self.failed.emit(traceback.format_exc())
        finally:
            self.finished.emit()


class BuildDialog(QDialog):
    def __init__(self, parent, language_code, mod_root):
        super().__init__(parent)
        self.words = TEXT[language_code]
        self.setWindowTitle(self.words["build_title"])
        self.setModal(True)
        self.setMinimumWidth(610)
        metadata = read_mod_metadata(mod_root)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 22, 22, 22)
        outer.setSpacing(16)
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)

        self.csv_edit = self._path_row(form, self.words["csv"], False)
        self.language_edit = QLineEdit("Russian")
        form.addRow(self.words["language"], self.language_edit)
        self.version_edit = QComboBox()
        versions = metadata["versions"] or ["1.6"]
        self.version_edit.addItems(versions)
        self.version_edit.setCurrentIndex(len(versions) - 1)
        self.version_edit.setEditable(True)
        form.addRow(self.words["version"], self.version_edit)
        self.output_edit = self._path_row(form, self.words["destination"], True)
        outer.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton(self.words["cancel"])
        cancel.clicked.connect(self.reject)
        create = QPushButton(self.words["create"])
        create.setObjectName("primary")
        create.clicked.connect(self._validate)
        buttons.addWidget(cancel)
        buttons.addWidget(create)
        outer.addLayout(buttons)

    def _path_row(self, form, label, directory):
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(7)
        edit = QLineEdit()
        button = QPushButton(self.words["choose"])
        button.clicked.connect(lambda: self._choose_path(edit, directory))
        row.addWidget(edit, 1)
        row.addWidget(button)
        form.addRow(label, container)
        return edit

    def _choose_path(self, edit, directory):
        if directory:
            selected = QFileDialog.getExistingDirectory(self, self.words["destination"])
        else:
            selected, _ = QFileDialog.getOpenFileName(
                self, self.words["choose_csv"], "", "CSV files (*.csv);;All files (*)"
            )
        if selected:
            edit.setText(selected)

    def _validate(self):
        valid = (
            os.path.isfile(self.csv_edit.text().strip())
            and bool(self.language_edit.text().strip())
            and bool(re.fullmatch(r"\d+\.\d+", self.version_edit.currentText().strip()))
            and os.path.isdir(self.output_edit.text().strip())
        )
        if not valid:
            QMessageBox.warning(self, self.words["build_title"], self.words["invalid_build"])
            return
        self.accept()

    def values(self):
        return {
            "csv": self.csv_edit.text().strip(),
            "language": self.language_edit.text().strip(),
            "version": self.version_edit.currentText().strip(),
            "output_parent": self.output_edit.text().strip(),
        }


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("RimWorldTranslator", "QtEdition")
        self.language_code = self.settings.value("language", "ru")
        self._thread = None
        self._worker = None
        self._last_metadata = None
        self.setAcceptDrops(True)
        self.setMinimumSize(820, 650)
        self.resize(1020, 790)
        self.setWindowIcon(make_app_icon())
        self._build_ui()
        self._apply_language()
        saved_path = self.settings.value("mod_root", "")
        if saved_path and os.path.isdir(saved_path):
            self.source_edit.setText(saved_path)
            self.inspect_source()

    def t(self, key, **values):
        return TEXT[self.language_code][key].format(**values)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(26, 22, 26, 22)
        outer.setSpacing(14)

        header = QHBoxLayout()
        mark = QLabel("R")
        mark.setAlignment(Qt.AlignCenter)
        mark.setFixedSize(48, 48)
        mark.setStyleSheet(
            "background:#7464f5;color:white;border-radius:14px;font-size:20pt;font-weight:800;"
        )
        header.addWidget(mark)
        heading = QVBoxLayout()
        heading.setSpacing(1)
        self.title_label = QLabel()
        self.title_label.setObjectName("title")
        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("subtitle")
        heading.addWidget(self.title_label)
        heading.addWidget(self.subtitle_label)
        header.addLayout(heading)
        header.addStretch()
        self.edition_badge = QLabel()
        self.edition_badge.setObjectName("badge")
        header.addWidget(self.edition_badge)
        self.language_button = QPushButton()
        self.language_button.setObjectName("language")
        self.language_button.clicked.connect(self.toggle_language)
        header.addWidget(self.language_button)
        outer.addLayout(header)

        self.source_card = QFrame()
        self.source_card.setObjectName("dropCard")
        self.source_card.setProperty("dragActive", False)
        card = QVBoxLayout(self.source_card)
        card.setContentsMargins(18, 16, 18, 16)
        card.setSpacing(10)
        self.source_label = QLabel()
        self.source_label.setObjectName("section")
        card.addWidget(self.source_label)
        path_row = QHBoxLayout()
        self.source_edit = QLineEdit()
        self.source_edit.editingFinished.connect(self.inspect_source)
        self.browse_button = QPushButton()
        self.browse_button.clicked.connect(self.browse_source)
        self.open_button = QPushButton()
        self.open_button.clicked.connect(self.open_source)
        path_row.addWidget(self.source_edit, 1)
        path_row.addWidget(self.browse_button)
        path_row.addWidget(self.open_button)
        card.addLayout(path_row)
        self.mod_name = QLabel()
        self.mod_name.setStyleSheet("font-size:12pt;font-weight:650;color:#ffffff;")
        self.mod_details = QLabel()
        self.mod_details.setObjectName("muted")
        self.mod_details.setWordWrap(True)
        card.addWidget(self.mod_name)
        card.addWidget(self.mod_details)
        outer.addWidget(self.source_card)

        advanced = QFrame()
        advanced.setObjectName("card")
        advanced_layout = QVBoxLayout(advanced)
        advanced_layout.setContentsMargins(18, 13, 18, 13)
        advanced_layout.setSpacing(7)
        self.tags_label = QLabel()
        self.tags_label.setObjectName("section")
        self.tags_edit = QLineEdit(self.settings.value("force_tags", ""))
        self.tags_edit.editingFinished.connect(self.save_settings)
        advanced_layout.addWidget(self.tags_label)
        advanced_layout.addWidget(self.tags_edit)
        outer.addWidget(advanced)

        actions = QHBoxLayout()
        self.export_button = QPushButton()
        self.export_button.setObjectName("primary")
        self.export_button.clicked.connect(self.export_csv)
        self.build_button = QPushButton()
        self.build_button.setObjectName("secondary")
        self.build_button.clicked.connect(self.build_mod)
        self.legacy_button = QPushButton()
        self.legacy_button.setObjectName("danger")
        self.legacy_button.clicked.connect(self.legacy_import)
        actions.addWidget(self.export_button)
        actions.addWidget(self.build_button)
        actions.addStretch()
        actions.addWidget(self.legacy_button)
        outer.addLayout(actions)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        outer.addWidget(self.progress)

        log_header = QHBoxLayout()
        self.log_label = QLabel()
        self.log_label.setObjectName("section")
        self.clear_button = QPushButton()
        self.clear_button.clicked.connect(lambda: self.log_view.clear())
        log_header.addWidget(self.log_label)
        log_header.addStretch()
        log_header.addWidget(self.clear_button)
        outer.addLayout(log_header)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(210)
        outer.addWidget(self.log_view, 1)

        status_row = QHBoxLayout()
        self.status_label = QLabel()
        self.status_label.setObjectName("muted")
        self.version_label = QLabel("v" + APP_VERSION)
        self.version_label.setObjectName("muted")
        self.about_button = QPushButton()
        self.about_button.setFlat(True)
        self.about_button.clicked.connect(self.show_about)
        status_row.addWidget(self.status_label)
        status_row.addStretch()
        status_row.addWidget(self.about_button)
        status_row.addWidget(self.version_label)
        outer.addLayout(status_row)

        self.busy_controls = [
            self.browse_button, self.export_button, self.build_button,
            self.legacy_button, self.source_edit,
        ]

    def _apply_language(self):
        self.setWindowTitle(self.t("title") + " — Qt")
        self.title_label.setText(self.t("title"))
        self.subtitle_label.setText(self.t("subtitle"))
        self.edition_badge.setText(self.t("modern"))
        self.language_button.setText("EN" if self.language_code == "ru" else "RU")
        self.source_label.setText(self.t("source"))
        self.source_edit.setPlaceholderText(self.t("source_hint"))
        self.browse_button.setText(self.t("browse"))
        self.open_button.setText(self.t("open"))
        self.tags_label.setText(self.t("extra_tags"))
        self.tags_edit.setPlaceholderText(self.t("extra_hint"))
        self.export_button.setText(self.t("export"))
        self.build_button.setText(self.t("build"))
        self.legacy_button.setText(self.t("legacy"))
        self.log_label.setText(self.t("log"))
        self.clear_button.setText(self.t("clear"))
        self.about_button.setText(self.t("about"))
        if self._thread is None:
            self.status_label.setText(self.t("ready"))
        self._show_metadata(self._last_metadata)

    def toggle_language(self):
        self.language_code = "en" if self.language_code == "ru" else "ru"
        self.settings.setValue("language", self.language_code)
        self._apply_language()

    def show_about(self):
        box = QMessageBox(self)
        box.setWindowTitle(self.t("about"))
        box.setText(self.t("about_text", version=APP_VERSION))
        box.setIconPixmap(make_app_icon().pixmap(64, 64))
        box.exec()

    def save_settings(self):
        self.settings.setValue("mod_root", self.source_edit.text().strip())
        self.settings.setValue("force_tags", self.tags_edit.text().strip())

    def browse_source(self):
        selected = QFileDialog.getExistingDirectory(self, self.t("choose_mod"))
        if selected:
            self.source_edit.setText(selected)
            self.inspect_source()

    def open_source(self):
        path = self.source_edit.text().strip()
        if os.path.isdir(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def valid_source(self):
        path = self.source_edit.text().strip().strip('"')
        if not os.path.isdir(path):
            QMessageBox.warning(self, self.t("source"), self.t("need_mod"))
            return ""
        self.source_edit.setText(os.path.abspath(path))
        self.save_settings()
        return self.source_edit.text()

    def inspect_source(self):
        source = self.valid_source()
        if not source or self._thread is not None:
            return
        self._start_task(
            lambda _progress, _log: inspect_mod(source),
            self.t("inspect"), self._inspection_done, quiet=True,
        )

    def _inspection_done(self, metadata):
        self._last_metadata = metadata
        self._show_metadata(metadata)

    def _show_metadata(self, metadata):
        if not metadata:
            self.mod_name.setText(self.t("unknown_mod"))
            self.mod_details.setText("")
            return
        package_id = metadata["package_id"] or "—"
        versions = ", ".join(metadata["versions"]) or "—"
        details = "  ·  ".join([
            self.t("xml_files", count=metadata.get("xml_count", 0)),
            self.t("package", package=package_id),
            self.t("versions", versions=versions),
        ])
        self.mod_name.setText(metadata["name"])
        self.mod_details.setText(details)

    def export_csv(self):
        source = self.valid_source()
        if not source:
            return
        default_path = os.path.join(os.path.dirname(source), "translations.csv")
        output, _ = QFileDialog.getSaveFileName(
            self, self.t("save_csv"), default_path, "CSV files (*.csv)"
        )
        if not output:
            return
        if not output.lower().endswith(".csv"):
            output += ".csv"
        tags = self.tags_edit.text().strip()
        self.log_view.clear()
        self._start_task(
            lambda progress, log: export_translations(source, output, tags, progress, log),
            self.t("exporting"),
            lambda result: self._show_result("export_done", result),
        )

    def build_mod(self):
        source = self.valid_source()
        if not source:
            return
        dialog = BuildDialog(self, self.language_code, source)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        output_root = os.path.join(
            values["output_parent"],
            default_translation_output(source, values["language"]),
        )
        if os.path.exists(output_root):
            output_root += "_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_view.clear()

        def task(progress, log):
            progress(15)
            log("CSV: " + values["csv"], "INFO")
            result = build_translation_package(
                source, values["csv"], output_root,
                values["language"], values["version"],
            )
            progress(100)
            log("Output: " + output_root, "SUCCESS")
            for warning in result["warnings"][:100]:
                log(warning, "WARNING")
            return result

        self._start_task(task, self.t("building"), lambda result: self._show_result("build_done", result))

    def legacy_import(self):
        source = self.valid_source()
        if not source:
            return
        answer = QMessageBox.warning(
            self, self.t("legacy_title"), self.t("legacy_warning"),
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return
        csv_path, _ = QFileDialog.getOpenFileName(
            self, self.t("choose_csv"), "", "CSV files (*.csv);;All files (*)"
        )
        if not csv_path:
            return
        self.log_view.clear()
        self._start_task(
            lambda progress, log: import_into_original(source, csv_path, progress, log),
            self.t("importing"),
            lambda result: self._show_result("import_done", result),
        )

    def _show_result(self, message_key, result):
        self.append_log(self.t(message_key, **result).replace("\n", " · "), "SUCCESS")
        QMessageBox.information(self, self.t("done"), self.t(message_key, **result))

    def _start_task(self, task, status, on_success, quiet=False):
        if self._thread is not None:
            return
        self.status_label.setText(status)
        self.progress.setValue(0)
        for control in self.busy_controls:
            control.setEnabled(False)
        if not quiet:
            self.append_log(status, "INFO")

        thread = QThread(self)
        worker = TaskWorker(task)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.progress.setValue)
        worker.log.connect(self.append_log)
        worker.succeeded.connect(on_success)
        worker.failed.connect(self._task_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._task_finished)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _task_failed(self, trace):
        last_line = trace.strip().splitlines()[-1] if trace.strip() else self.t("error")
        self.append_log(trace, "ERROR")
        QMessageBox.critical(self, self.t("error"), last_line)

    def _task_finished(self):
        self._thread = None
        self._worker = None
        self.progress.setValue(0)
        self.status_label.setText(self.t("ready"))
        for control in self.busy_controls:
            control.setEnabled(True)

    @Slot(str, str)
    def append_log(self, message, level="INFO"):
        colors = {
            "INFO": "#c7cbd5", "SUCCESS": "#71d6b7",
            "WARNING": "#e6bd6a", "ERROR": "#ef7f88",
        }
        timestamp = datetime.now().strftime("%H:%M:%S")
        safe_message = html.escape(str(message)).replace("\n", "<br>")
        self.log_view.append(
            '<span style="color:#697184">[' + timestamp + "]</span> "
            '<span style="color:' + colors.get(level, colors["INFO"]) + '">'
            + safe_message + "</span>"
        )

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
            self.source_card.setProperty("dragActive", True)
            self.source_card.style().unpolish(self.source_card)
            self.source_card.style().polish(self.source_card)
            self.status_label.setText(self.t("drop"))

    def dragLeaveEvent(self, event):
        self._reset_drag_style()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._reset_drag_style()
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isdir(path):
                self.source_edit.setText(path)
                self.inspect_source()
                event.acceptProposedAction()
                return

    def _reset_drag_style(self):
        self.source_card.setProperty("dragActive", False)
        self.source_card.style().unpolish(self.source_card)
        self.source_card.style().polish(self.source_card)
        if self._thread is None:
            self.status_label.setText(self.t("ready"))

    def closeEvent(self, event):
        self.save_settings()
        if self._thread is not None:
            event.ignore()
            return
        super().closeEvent(event)


def make_app_icon():
    pixmap = QPixmap(128, 128)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#7464f5"))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(4, 4, 120, 120, 30, 30)
    painter.setPen(QColor("white"))
    font = QFont("Segoe UI", 58, QFont.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "R")
    painter.end()
    return QIcon(pixmap)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("RimWorld Mod Translator Qt")
    app.setOrganizationName("RimWorldTranslator")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
