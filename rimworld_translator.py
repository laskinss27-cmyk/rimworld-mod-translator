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


DEFAULT_WHITE_LIST = (
    "label, description, labelNoun, text, name, title, message, "
    "tip, help, info, desc, tooltip, string, entry, button, menu"
)


class RimWorldTranslator:
    def __init__(self, root):
        self.root = root
        self.root.title("RimWorld Mod Translator")
        self.root.geometry("900x700")

        self.source_dir = tk.StringVar()
        self.white_list_tags = tk.StringVar(value=DEFAULT_WHITE_LIST)
        self.settings_file = "translator_settings.json"

        self.load_settings()
        self.setup_ui()

    def load_settings(self):
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                    self.white_list_tags.set(
                        settings.get("white_list_tags", DEFAULT_WHITE_LIST)
                    )
        except Exception as e:
            print(f"Ошибка загрузки настроек: {e}")

    def save_settings(self):
        try:
            settings = {"white_list_tags": self.white_list_tags.get()}
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

        ttk.Label(main_frame, text="Папка с модами:").grid(
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

        ttk.Label(main_frame, text="Белый список тегов (через запятую):").grid(
            row=1, column=0, sticky=tk.W, pady=5
        )
        tags_frame = ttk.Frame(main_frame)
        tags_frame.grid(row=1, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        tags_frame.columnconfigure(0, weight=1)

        ttk.Entry(tags_frame, textvariable=self.white_list_tags).grid(
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

        ttk.Label(main_frame, text="Лог выполнения:").grid(
            row=4, column=0, sticky=tk.W, pady=5
        )

        self.log_text = scrolledtext.ScrolledText(main_frame, height=25, wrap=tk.WORD)
        self.log_text.grid(
            row=5, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5
        )

        self.setup_context_menu()

        self.status_var = tk.StringVar(value="Готов к работе")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
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
        except Exception as e:
            print(f"Ошибка контекстного меню: {e}")

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
        directory = filedialog.askdirectory(title="Выберите папку с модами RimWorld")
        if directory:
            self.source_dir.set(directory)
            self.log(f"Выбрана папка: {directory}")

    def open_directory(self):
        directory = self.source_dir.get()
        if not directory or not os.path.exists(directory):
            messagebox.showwarning("Предупреждение", "Сначала выберите папку с модами")
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
        except Exception as e:
            print(f"Ошибка логирования: {e}")

    def clear_log(self):
        self.log_text.delete(1.0, tk.END)

    def update_progress(self, value, maximum=100):
        self.progress["value"] = value
        self.progress["maximum"] = maximum
        self.root.update_idletasks()

    def get_white_list(self):
        tags = [tag.strip().lower() for tag in self.white_list_tags.get().split(",")]
        return [tag for tag in tags if tag]

    def find_xml_files(self, directory):
        xml_files = []
        try:
            for root_dir, dirs, files in os.walk(directory):
                if any(skip in root_dir.lower() for skip in [".git", ".vs", "bin", "obj"]):
                    continue
                for file in files:
                    if file.lower().endswith(".xml"):
                        xml_files.append(os.path.join(root_dir, file))
        except Exception as e:
            self.log(f"Ошибка поиска XML файлов: {e}", "ERROR")
        return xml_files

    def export_text(self):
        if not self.source_dir.get() or not os.path.exists(self.source_dir.get()):
            messagebox.showerror("Ошибка", "Сначала выберите папку с модами")
            return

        self.clear_log()
        self.status_var.set("Экспорт текста...")
        self.update_progress(0)

        try:
            white_list = self.get_white_list()
            if not white_list:
                messagebox.showerror("Ошибка", "Белый список тегов не может быть пустым")
                return

            self.log(f"Начал экспорт текста из папки: {self.source_dir.get()}")
            self.log(f"Используется белый список тегов: {', '.join(white_list)}")

            xml_files = self.find_xml_files(self.source_dir.get())
            self.log(f"Найдено XML файлов: {len(xml_files)}")

            if not xml_files:
                self.log("Не найдено XML файлов для обработки", "WARNING")
                messagebox.showwarning("Предупреждение", "Не найдено XML файлов для обработки")
                return

            output_file = "translations.csv"
            total_text_units = 0
            processed_files = 0

            with open(output_file, "w", encoding="utf-8-sig", newline="") as csvfile:
                writer = csv.writer(
                    csvfile, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL
                )
                writer.writerow(
                    ["File", "Tag", "XPath", "Original Text", "Translation", "Attributes"]
                )

                for i, xml_file in enumerate(xml_files):
                    try:
                        relative_path = os.path.relpath(xml_file, self.source_dir.get())
                        self.log(f"Обработка: {relative_path}")
                        text_units = self.process_xml_file_to_csv(
                            xml_file, white_list, writer
                        )
                        total_text_units += text_units
                        processed_files += 1
                        progress = (i + 1) / len(xml_files) * 100
                        self.update_progress(progress)
                        self.status_var.set(
                            f"Обработано файлов: {i + 1}/{len(xml_files)}"
                        )
                    except Exception as e:
                        self.log(f"ОШИБКА в файле {xml_file}: {str(e)}", "ERROR")

            self.log(f"Экспорт завершен! Создан файл: {output_file}", "SUCCESS")
            self.log(f"Обработано файлов: {processed_files}/{len(xml_files)}")
            self.log(f"Найдено текстовых блоков: {total_text_units}")
            self.status_var.set(f"Экспорт завершен! Текстовых блоков: {total_text_units}")
            self.update_progress(0)

            messagebox.showinfo(
                "Готово",
                f"Экспорт завершен!\n"
                f"Файл: {output_file}\n"
                f"Текстовых блоков: {total_text_units}\n\n"
                f"Откройте файл в Google Sheets:\n"
                f"1. Переведите текст в колонке 'Translation'\n"
                f"   формулой =GOOGLETRANSLATE(D2; \"auto\"; \"ru\")\n"
                f"2. Скачайте обратно как CSV\n"
                f"3. Используйте 'Импортировать перевод'",
            )
        except Exception as e:
            error_msg = f"Критическая ошибка при экспорте: {str(e)}"
            self.log(error_msg, "ERROR")
            messagebox.showerror("Ошибка", error_msg)
            self.status_var.set("Ошибка при экспорте")
            self.update_progress(0)

    def process_xml_file_to_csv(self, xml_file, white_list, csv_writer):
        text_units_count = 0
        relative_path = os.path.relpath(xml_file, self.source_dir.get())

        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()

            for elem in root.iter():
                if not isinstance(elem.tag, str):
                    continue
                tag_name = elem.tag.lower()
                if tag_name not in white_list:
                    continue
                if not elem.text or not elem.text.strip():
                    continue

                original_text = elem.text.strip()
                if self.is_technical_text(original_text):
                    continue

                xpath = f"//{elem.tag}"
                attribs_str = (
                    "; ".join(f"{k}={v}" for k, v in elem.attrib.items())
                    if elem.attrib
                    else ""
                )

                csv_writer.writerow(
                    [relative_path, elem.tag, xpath, original_text, "", attribs_str]
                )
                text_units_count += 1

        except ET.ParseError as e:
            self.log(f"ОШИБКА парсинга XML в файле {xml_file}: {str(e)}", "ERROR")
        except Exception as e:
            self.log(f"Ошибка обработки файла {xml_file}: {str(e)}", "ERROR")

        return text_units_count

    def is_technical_text(self, text):
        if not text or not text.strip():
            return True
        if text.replace(".", "").replace(",", "").isdigit():
            return True
        if text.lower() in ("true", "false", "yes", "no", "null", "none"):
            return True
        if any(char in text for char in ["/", "\\", "@", "#", "$"]):
            if len(text) < 50:
                return True
        if re.match(
            r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
            text,
            re.I,
        ):
            return True
        return False

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
            messagebox.showerror("Ошибка", "Сначала выберите папку с модами")
            return

        csv_file = filedialog.askopenfilename(
            title="Выберите файл перевода (translations.csv)",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not csv_file:
            return

        self.clear_log()
        self.status_var.set("Импорт перевода...")
        self.update_progress(0)

        try:
            self.log(f"Начал импорт перевода из файла: {csv_file}")

            by_file = defaultdict(list)
            total_rows = 0
            with open(csv_file, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
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

            if not by_file:
                self.log("Не найдено переводов для импорта", "WARNING")
                messagebox.showwarning("Предупреждение", "Не найдено переводов для импорта")
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
                    applied, skipped = self.apply_translations_to_file(full_path, items)
                    applied_units += applied
                    skipped_units += skipped
                    if applied > 0:
                        updated_files += 1
                        self.log(f"{file_path}: применено {applied} переводов")
                except Exception as e:
                    self.log(f"ОШИБКА в файле {file_path}: {str(e)}", "ERROR")
                    skipped_units += len(items)

                progress = (i + 1) / file_count * 100
                self.update_progress(progress)
                self.status_var.set(f"Обновлено файлов: {i + 1}/{file_count}")

            self.log(
                f"Импорт завершен! Обновлено файлов: {updated_files}", "SUCCESS"
            )
            self.log(f"Применено переводов: {applied_units}")
            if skipped_units:
                self.log(f"Пропущено переводов: {skipped_units}", "WARNING")
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
            error_msg = f"Критическая ошибка при импорте: {str(e)}"
            self.log(error_msg, "ERROR")
            messagebox.showerror("Ошибка", error_msg)
            self.status_var.set("Ошибка при импорте")
            self.update_progress(0)

    def apply_translations_to_file(self, xml_file, items):
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
        except ET.ParseError as e:
            self.log(f"ОШИБКА парсинга XML в файле {xml_file}: {str(e)}", "ERROR")
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
