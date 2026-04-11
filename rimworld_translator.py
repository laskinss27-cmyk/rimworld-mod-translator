import os
import subprocess
import platform
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from datetime import datetime
import re
import json
import csv
from collections import defaultdict


BLACKLIST_TAGS = {
    "defname", "parentname", "abstract",
    "thingclass", "workerclass", "inspectorclass", "compclass",
    "thinkclass", "jobclass", "lordclass", "worldobjectclass",
    "mentalstateclass", "stateclass", "driverclass", "mapclass",
    "tickertype", "altitudelayer", "passability", "linkflags",
    "designationcategory", "thingcategory", "shadertype",
    "typeof", "markdef", "wreckeddef",
}

BLACKLIST_SUFFIXES = ("class", "path", "def", "defs")
BLACKLIST_PREFIXES = ("sound",)

KNOWN_TEXT_TAGS = {
    "label", "description", "labelnoun", "labelshort",
    "text", "name", "title", "message", "customlabel",
    "tip", "help", "info", "desc", "tooltip",
    "string", "entry", "button", "menu",
    "gerund", "summary", "report", "noun",
    "lettertext", "letterlabel", "rulestext",
    "fixedname", "pawnlabel", "headerimage",
    "jobstring", "verb", "gerundlabel",
    "labelMale", "labelFemale", "labelMechanoids",
    "beginletter", "beginletterdef", "helptext",
    "recoveryMessage", "baseInspectLine",
    "description", "reportstring", "toil",
    "ingestcommandstring", "ingestReportString",
    "offMessage", "arrivalTextEnemy", "arrivalTextFriendly",
    "letterLabel", "letterText", "approachOrderString",
    "approachingReportString", "arrivedLetterLabel",
    "arrivedLetterText", "pawnsCanGainRoyalTitle",
    "discoveredLetterText", "discoveredLetterTitle",
    "successfullyRemovedHediffMessage",
}


def is_blacklisted_tag(tag_name):
    low = tag_name.lower()
    if low in BLACKLIST_TAGS:
        return True
    for suffix in BLACKLIST_SUFFIXES:
        if low.endswith(suffix) and low != suffix:
            return True
    for prefix in BLACKLIST_PREFIXES:
        if low.startswith(prefix):
            return True
    return False


def is_definitely_technical(text):
    t = text.strip()
    if not t:
        return True
    if re.match(r"^-?\d+([.,]\d+)?f?$", t):
        return True
    if t.lower() in ("true", "false", "null", "none"):
        return True
    if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}", t, re.I):
        return True
    if re.match(r"^[A-Z]\w+(\.[A-Z]\w+)+$", t):
        return True
    if re.match(r"^(\w+[/\\])+\w+(\.\w+)?$", t):
        return True
    if t.startswith("<") or t.startswith("{"):
        return True
    if re.match(r"^\(\d+,\s*\d+\)$", t):
        return True
    if re.match(r"^#[0-9a-fA-F]{6,8}$", t):
        return True
    if re.match(r"^\d+x\d+$", t):
        return True
    return False


def is_definitely_text(text):
    t = text.strip()
    words = t.split()
    if len(words) >= 3:
        return True
    if len(t) > 1 and t[-1] in ".!?…»\"'":
        return True
    if len(words) == 2 and any(w[0:1].islower() for w in words):
        return True
    if len(t) > 60:
        return True
    if "\n" in text.strip():
        return True
    return False


def is_likely_text(text, tag_name):
    t = text.strip()
    if re.match(r"^[A-Z][a-z]+([A-Z][a-z]+)+\d*$", t):
        return False
    if re.match(r"^[a-z]+[A-Z]", t):
        return False
    if "_" in t and " " not in t:
        return False
    if t.isupper() and len(t) > 2 and " " not in t:
        return False
    if tag_name.lower() in KNOWN_TEXT_TAGS:
        return True
    if re.match(r"^[A-Z]?[a-zа-яё]+$", t) and len(t) >= 2:
        return True
    words = t.split()
    if len(words) == 2:
        return True
    return False


def is_translatable(tag_name, text, known_ids):
    if is_blacklisted_tag(tag_name):
        return False
    t = text.strip()
    if not t:
        return False
    if is_definitely_technical(t):
        return False
    if is_definitely_text(t):
        return True
    if t in known_ids:
        return False
    return is_likely_text(t, tag_name)


def collect_identifiers(xml_files):
    ids = set()
    for xml_file in xml_files:
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            for elem in root.iter():
                if not isinstance(elem.tag, str):
                    continue
                low = elem.tag.lower()
                if low == "defname":
                    if elem.text and elem.text.strip():
                        ids.add(elem.text.strip())
                elif low.endswith("def") or low.endswith("defs"):
                    if elem.text and elem.text.strip():
                        val = elem.text.strip()
                        if not " " in val and re.match(r"^[A-Za-z_]\w*$", val):
                            ids.add(val)
                elif low == "li":
                    if elem.text and elem.text.strip():
                        val = elem.text.strip()
                        if re.match(r"^[A-Z][a-zA-Z0-9_]+$", val) and " " not in val:
                            ids.add(val)
        except Exception:
            pass
    return ids


def load_existing_translations(csv_path):
    translations = {}
    if not os.path.exists(csv_path):
        return translations
    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                file_path = (row.get("File") or "").strip()
                original = row.get("Original Text") or ""
                translation = row.get("Translation") or ""
                if file_path and original and translation.strip():
                    key = (file_path, original)
                    translations[key] = translation
    except Exception:
        pass
    return translations


class RimWorldTranslator:
    def __init__(self, root):
        self.root = root
        self.root.title("RimWorld Mod Translator v2.0")
        self.root.geometry("900x700")

        self.source_dir = tk.StringVar()
        self.force_tags = tk.StringVar(value="")
        self.settings_file = "translator_settings.json"

        self.load_settings()
        self.setup_ui()

    def load_settings(self):
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                    self.force_tags.set(settings.get("force_tags", ""))
        except Exception as e:
            print(f"Ошибка загрузки настроек: {e}")

    def save_settings(self):
        try:
            settings = {"force_tags": self.force_tags.get()}
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            self.log("Настройки сохранены", "SUCCESS")
        except Exception as e:
            self.log(f"Ошибка сохранения настроек: {e}", "ERROR")

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(5, weight=1)

        ttk.Label(main_frame, text="Папка мода:").grid(
            row=0, column=0, sticky=tk.W, pady=5
        )
        dir_frame = ttk.Frame(main_frame)
        dir_frame.grid(row=0, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        dir_frame.columnconfigure(0, weight=1)

        ttk.Entry(dir_frame, textvariable=self.source_dir).grid(
            row=0, column=0, sticky=(tk.W, tk.E)
        )
        ttk.Button(dir_frame, text="Обзор...", command=self.browse_directory).grid(
            row=0, column=1, padx=5
        )
        ttk.Button(dir_frame, text="📁", command=self.open_directory, width=3).grid(
            row=0, column=2
        )

        ttk.Label(
            main_frame, text="Доп. теги для перевода (необязательно):"
        ).grid(row=1, column=0, sticky=tk.W, pady=5)
        tags_frame = ttk.Frame(main_frame)
        tags_frame.grid(row=1, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        tags_frame.columnconfigure(0, weight=1)

        ttk.Entry(tags_frame, textvariable=self.force_tags).grid(
            row=0, column=0, sticky=(tk.W, tk.E)
        )

        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=10)

        ttk.Button(
            button_frame,
            text="Экспортировать в CSV",
            command=self.export_text,
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            button_frame,
            text="Импортировать перевод",
            command=self.import_translation,
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            button_frame,
            text="Сохранить настройки",
            command=self.save_settings,
        ).pack(side=tk.LEFT, padx=5)

        self.progress = ttk.Progressbar(main_frame, mode="determinate")
        self.progress.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        ttk.Label(main_frame, text="Лог:").grid(
            row=4, column=0, sticky=tk.W, pady=5
        )

        self.log_text = scrolledtext.ScrolledText(main_frame, height=25, wrap=tk.WORD)
        self.log_text.grid(
            row=5, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5
        )

        self.setup_context_menu()

        self.status_var = tk.StringVar(value="Готов к работе")
        status_bar = ttk.Label(
            main_frame, textvariable=self.status_var, relief=tk.SUNKEN
        )
        status_bar.grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

    def setup_context_menu(self):
        self.context_menu = tk.Menu(self.log_text, tearoff=0)
        self.context_menu.add_command(label="Копировать", command=self.copy_log)
        self.context_menu.add_command(label="Выделить все", command=self.select_all_log)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Очистить лог", command=self.clear_log)
        self.log_text.bind("<Button-3>", self.show_context_menu)

    def show_context_menu(self, event):
        try:
            self.context_menu.post(event.x_root, event.y_root)
        except Exception:
            pass

    def copy_log(self):
        try:
            selected_text = self.log_text.get(tk.SEL_FIRST, tk.SEL_LAST)
            self.root.clipboard_clear()
            self.root.clipboard_append(selected_text)
        except tk.TclError:
            pass

    def select_all_log(self):
        self.log_text.tag_add(tk.SEL, "1.0", tk.END)
        self.log_text.mark_set(tk.INSERT, "1.0")
        self.log_text.see(tk.INSERT)

    def browse_directory(self):
        directory = filedialog.askdirectory(title="Выберите папку мода RimWorld")
        if directory:
            self.source_dir.set(directory)
            self.log(f"Выбрана папка: {directory}")

    def open_directory(self):
        directory = self.source_dir.get()
        if not directory or not os.path.exists(directory):
            messagebox.showwarning("Предупреждение", "Сначала выберите папку мода")
            return
        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(directory)
            elif system == "Darwin":
                subprocess.Popen(["open", directory])
            else:
                subprocess.Popen(["xdg-open", directory])
        except Exception as e:
            self.log(f"Не удалось открыть папку: {e}", "ERROR")

    def log(self, message, level="INFO"):
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            color_map = {
                "INFO": "black",
                "WARNING": "darkorange",
                "ERROR": "red",
                "SUCCESS": "green",
            }
            color = color_map.get(level, "black")
            log_message = f"[{timestamp}] {message}\n"
            self.log_text.insert(tk.END, log_message)
            self.log_text.tag_configure(color, foreground=color)
            start_index = self.log_text.index("end-2l")
            end_index = self.log_text.index("end-1l")
            self.log_text.tag_add(color, start_index, end_index)
            self.log_text.see(tk.END)
            self.root.update_idletasks()
        except Exception:
            pass

    def clear_log(self):
        self.log_text.delete(1.0, tk.END)

    def update_progress(self, value, maximum=100):
        self.progress["value"] = value
        self.progress["maximum"] = maximum
        self.root.update_idletasks()

    def get_force_tags(self):
        tags = [t.strip().lower() for t in self.force_tags.get().split(",")]
        return {t for t in tags if t}

    def find_xml_files(self, directory):
        xml_files = []
        skip = {".git", ".vs", "bin", "obj", "__pycache__"}
        try:
            for root_dir, dirs, files in os.walk(directory):
                if any(s in root_dir.lower() for s in skip):
                    continue
                for f in files:
                    if f.lower().endswith(".xml"):
                        xml_files.append(os.path.join(root_dir, f))
        except Exception as e:
            self.log(f"Ошибка поиска XML файлов: {e}", "ERROR")
        return xml_files

    def export_text(self):
        if not self.source_dir.get() or not os.path.exists(self.source_dir.get()):
            messagebox.showerror("Ошибка", "Сначала выберите папку мода")
            return

        self.clear_log()
        self.status_var.set("Экспорт текста...")
        self.update_progress(0)

        try:
            self.log(f"Папка мода: {self.source_dir.get()}")

            xml_files = self.find_xml_files(self.source_dir.get())
            self.log(f"Найдено XML файлов: {len(xml_files)}")

            if not xml_files:
                self.log("XML файлы не найдены", "WARNING")
                messagebox.showwarning("Предупреждение", "XML файлы не найдены")
                return

            self.log("Проход 1: сбор идентификаторов (defName, ссылки)...")
            self.status_var.set("Сбор идентификаторов...")
            known_ids = collect_identifiers(xml_files)
            self.log(f"Найдено идентификаторов: {len(known_ids)}")

            force = self.get_force_tags()
            if force:
                self.log(f"Принудительные теги: {', '.join(force)}")

            output_file = "translations.csv"
            old_translations = load_existing_translations(output_file)
            if old_translations:
                self.log(
                    f"Найдено предыдущих переводов: {len(old_translations)} (smart merge)",
                    "SUCCESS",
                )

            self.log("Проход 2: извлечение текста для перевода...")
            total_units = 0
            new_units = 0
            merged_units = 0
            processed_files = 0
            seen_keys = set()

            with open(output_file, "w", encoding="utf-8-sig", newline="") as csvfile:
                writer = csv.writer(
                    csvfile, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL
                )
                writer.writerow(
                    [
                        "File",
                        "Tag",
                        "XPath",
                        "Original Text",
                        "Translation",
                        "Status",
                    ]
                )

                for i, xml_file in enumerate(xml_files):
                    try:
                        relative_path = os.path.relpath(
                            xml_file, self.source_dir.get()
                        )
                        units = self.extract_from_file(
                            xml_file,
                            relative_path,
                            known_ids,
                            force,
                            old_translations,
                            seen_keys,
                            writer,
                        )
                        file_total, file_new, file_merged = units
                        total_units += file_total
                        new_units += file_new
                        merged_units += file_merged
                        if file_total > 0:
                            processed_files += 1
                            self.log(f"  {relative_path}: {file_total} строк")
                        progress = (i + 1) / len(xml_files) * 100
                        self.update_progress(progress)
                        self.status_var.set(
                            f"Файлов: {i + 1}/{len(xml_files)}"
                        )
                    except Exception as e:
                        self.log(f"ОШИБКА: {xml_file}: {str(e)}", "ERROR")

                unused_count = 0
                for (file_path, original), translation in old_translations.items():
                    if (file_path, original) not in seen_keys:
                        writer.writerow(
                            [file_path, "", "", original, translation, "UNUSED"]
                        )
                        unused_count += 1

            self.log("---", "INFO")
            self.log(f"Всего строк для перевода: {total_units}", "SUCCESS")
            self.log(f"  Новых: {new_units}")
            self.log(f"  Из прошлого перевода: {merged_units}")
            if unused_count:
                self.log(
                    f"  Устаревших (UNUSED): {unused_count}",
                    "WARNING",
                )
            self.log(f"Файлов с текстом: {processed_files}/{len(xml_files)}")
            self.log(f"Файл сохранён: {output_file}", "SUCCESS")
            self.status_var.set(
                f"Готово. Строк: {total_units} (новых: {new_units})"
            )
            self.update_progress(0)

            messagebox.showinfo(
                "Готово",
                f"Экспорт завершен!\n"
                f"Файл: {output_file}\n"
                f"Строк: {total_units} (новых: {new_units}, "
                f"из прошлого: {merged_units})\n\n"
                f"Колонка Status:\n"
                f"  NEW = нужен перевод\n"
                f"  DONE = уже переведено (smart merge)\n"
                f"  UNUSED = строка удалена из мода\n\n"
                f"Google Sheets:\n"
                f"  =GOOGLETRANSLATE(D2; \"auto\"; \"ru\")",
            )
        except Exception as e:
            self.log(f"Критическая ошибка: {str(e)}", "ERROR")
            messagebox.showerror("Ошибка", str(e))
            self.status_var.set("Ошибка при экспорте")
            self.update_progress(0)

    def extract_from_file(
        self,
        xml_file,
        relative_path,
        known_ids,
        force_tags,
        old_translations,
        seen_keys,
        csv_writer,
    ):
        total = 0
        new = 0
        merged = 0

        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
        except ET.ParseError as e:
            self.log(f"Ошибка парсинга: {relative_path}: {e}", "ERROR")
            return (0, 0, 0)
        except Exception as e:
            self.log(f"Ошибка чтения: {relative_path}: {e}", "ERROR")
            return (0, 0, 0)

        for elem in root.iter():
            if not isinstance(elem.tag, str):
                continue
            if not elem.text or not elem.text.strip():
                continue

            tag_name = elem.tag
            text = elem.text.strip()
            tag_low = tag_name.lower()

            forced = tag_low in force_tags
            if forced and not is_definitely_technical(text):
                pass
            elif not is_translatable(tag_name, text, known_ids):
                continue

            xpath = f"//{tag_name}"
            key = (relative_path, text)
            seen_keys.add(key)

            old_translation = old_translations.get(key, "")
            if old_translation:
                status = "DONE"
                merged += 1
            else:
                status = "NEW"
                new += 1

            csv_writer.writerow(
                [relative_path, tag_name, xpath, text, old_translation, status]
            )
            total += 1

        return (total, new, merged)

    def indent_xml(self, elem, level=0):
        i = "\n" + level * "  "
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
            for child in elem:
                self.indent_xml(child, level + 1)
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = i

    def import_translation(self):
        if not self.source_dir.get() or not os.path.exists(self.source_dir.get()):
            messagebox.showerror("Ошибка", "Сначала выберите папку мода")
            return

        csv_file = filedialog.askopenfilename(
            title="Выберите файл перевода",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not csv_file:
            return

        self.clear_log()
        self.status_var.set("Импорт перевода...")
        self.update_progress(0)

        try:
            self.log(f"Файл перевода: {csv_file}")

            by_file = defaultdict(list)
            total_rows = 0
            skipped_unused = 0

            with open(csv_file, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    status = (row.get("Status") or "").strip().upper()
                    if status == "UNUSED":
                        skipped_unused += 1
                        continue

                    file_path = (row.get("File") or "").strip()
                    tag = (row.get("Tag") or "").strip()
                    original_text = row.get("Original Text") or ""
                    translated_text = row.get("Translation") or ""

                    if not file_path or not tag:
                        continue
                    if not translated_text.strip():
                        continue

                    by_file[file_path].append(
                        (tag, original_text, translated_text)
                    )
                    total_rows += 1

            self.log(f"Загружено переводов: {total_rows}")
            if skipped_unused:
                self.log(f"Пропущено устаревших (UNUSED): {skipped_unused}")

            if not by_file:
                self.log("Нет переводов для импорта", "WARNING")
                messagebox.showwarning("Предупреждение", "Нет переводов для импорта")
                return

            updated_files = 0
            applied_units = 0
            skipped_units = 0
            file_count = len(by_file)

            for i, (file_path, items) in enumerate(by_file.items()):
                full_path = os.path.join(self.source_dir.get(), file_path)
                if not os.path.exists(full_path):
                    self.log(f"Файл не найден: {file_path}", "WARNING")
                    skipped_units += len(items)
                    continue
                try:
                    applied, skipped = self.apply_translations_to_file(
                        full_path, items
                    )
                    applied_units += applied
                    skipped_units += skipped
                    if applied > 0:
                        updated_files += 1
                        self.log(f"  {file_path}: {applied} переводов")
                except Exception as e:
                    self.log(f"ОШИБКА: {file_path}: {str(e)}", "ERROR")
                    skipped_units += len(items)

                progress = (i + 1) / file_count * 100
                self.update_progress(progress)
                self.status_var.set(f"Файлов: {i + 1}/{file_count}")

            self.log("---")
            self.log(
                f"Импорт завершен! Файлов: {updated_files}, "
                f"переводов: {applied_units}",
                "SUCCESS",
            )
            if skipped_units:
                self.log(f"Не удалось применить: {skipped_units}", "WARNING")
            self.status_var.set(
                f"Готово. Файлов: {updated_files}, переводов: {applied_units}"
            )
            self.update_progress(0)

            messagebox.showinfo(
                "Готово",
                f"Импорт завершен!\n"
                f"Обновлено файлов: {updated_files}\n"
                f"Применено переводов: {applied_units}",
            )
        except Exception as e:
            self.log(f"Критическая ошибка: {str(e)}", "ERROR")
            messagebox.showerror("Ошибка", str(e))
            self.status_var.set("Ошибка при импорте")
            self.update_progress(0)

    def apply_translations_to_file(self, xml_file, items):
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
        except ET.ParseError as e:
            self.log(f"Ошибка парсинга: {xml_file}: {e}", "ERROR")
            return 0, len(items)

        pending = defaultdict(list)
        for tag, original_text, translated_text in items:
            pending[(tag, original_text)].append(translated_text)

        applied = 0
        for elem in root.iter():
            if not isinstance(elem.tag, str):
                continue
            if not elem.text or not elem.text.strip():
                continue
            key = (elem.tag, elem.text.strip())
            if key in pending and pending[key]:
                elem.text = pending[key].pop(0)
                applied += 1

        skipped = sum(len(v) for v in pending.values())

        if applied > 0:
            self.indent_xml(root)
            with open(xml_file, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
                tree.write(f, encoding="unicode")

        return applied, skipped


def main():
    try:
        root = tk.Tk()
        app = RimWorldTranslator(root)
        root.mainloop()
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        input("Нажмите Enter для выхода...")


if __name__ == "__main__":
    main()
