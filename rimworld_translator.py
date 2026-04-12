import os
import subprocess
import platform
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
import re
import json
import csv
from collections import defaultdict

# ── DPI awareness (Windows) ───────────────────────────────────────────────────
try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_]\w*\}|\[[A-Za-z_]\w*\]")


# ── Placeholder helpers ───────────────────────────────────────────────────────

def mask_placeholders(text):
    holders = PLACEHOLDER_RE.findall(text)
    if not holders:
        return text, ""
    mapping = {}
    for i, h in enumerate(holders):
        if h not in mapping:
            mapping[h] = f"{{{i}}}"
    masked = text
    for original, token in mapping.items():
        masked = masked.replace(original, token)
    map_str = "; ".join(f"{v}={k}" for k, v in mapping.items())
    return masked, map_str


def unmask_placeholders(text, map_str):
    if not map_str or not map_str.strip():
        return text
    result = text
    for pair in map_str.split(";"):
        pair = pair.strip()
        if "=" not in pair:
            continue
        token, original = pair.split("=", 1)
        result = result.replace(token.strip(), original.strip())
    return result


# ── Tag rules ─────────────────────────────────────────────────────────────────

BLACKLIST_TAGS = {
    # Core engine tags
    "defname", "parentname", "abstract",
    "thingclass", "workerclass", "inspectorclass", "compclass",
    "thinkclass", "jobclass", "lordclass", "worldobjectclass",
    "mentalstateclass", "stateclass", "driverclass", "mapclass",
    "tickertype", "altitudelayer", "passability", "linkflags",
    "designationcategory", "thingcategory", "shadertype",
    "typeof", "markdef", "wreckeddef",
    # Slot / backstory / body-structure / enum-like tags
    "slot", "backstorycategory", "bodypartgroup", "appliedonfixtags",
    "height", "depth", "coverage", "groups", "woundanchortag",
    # Enum / code-value tags
    "paramupdatemode", "filterproperty", "capacity", "category",
    "terrainaffordanceneeded", "tradeability", "hediff", "workskill",
    "minqualityforartistic", "modifier", "hediffsolid", "pawntype",
    "movementtype", "techlevel", "effectworking", "armorcategory",
    "rotdrawmode", "debuglabel", "success", "linkedbodypartsgroup",
    "explosivedamagetype", "tag", "stat", "surfacetype",
    "repaireffect", "worktype", "priority", "overrideminifiedrot",
    "developmentalstagefilter", "destination", "resourcereadoutpriority",
    "price", "hediffskin",
    # Visual / render tags
    "colorchannel", "drawposition", "skinshader", "rendertree",
    "appearance", "linktype", "parent",
    # AI / behaviour tags
    "maxdanger", "impactsoundtype", "joykind", "tagtogive",
    "thinktreemain", "intelligence", "need",
    "moodrecoverythought", "defaultlocomotion",
    "alloweddevelopmentalstages", "partnerrace",
    # Reference / pointer tags
    "hatcherpawn", "usemeatfrom", "body", "purpose",
    "savekeysprefix", "harvesttag", "knowledgecategory",
    "treecategory", "researchprerequisite", "faction",
    "defaultfactiontype", "defaultbodypart",
    "warmupeffecter", "addtolist", "worktableroomrole",
    "allowedspectatorsides", "debuglabelextra", "titlerequired",
    # Script / quest logic tags
    "outcome", "storeas", "delayticks", "insigtop",
    # Coordinate / visual tags
    "volume", "rect", "drawoffset", "dooroffset",
    "texturescale", "minifieddrawoffset", "weapondrawoffset",
}

BLACKLIST_SUFFIXES = (
    "class", "path", "def", "defs", "color", "size", "offset",
    "shader", "type", "tag", "channel",
)
BLACKLIST_PREFIXES = ("sound", "render", "default")

KNOWN_TEXT_TAGS = {
    "label", "description", "labelnoun", "labelshort",
    "text", "name", "title", "message", "customlabel",
    "tip", "help", "info", "desc", "tooltip",
    "string", "entry", "button", "menu",
    "gerund", "summary", "report", "noun",
    "lettertext", "letterlabel", "rulestext",
    "fixedname", "pawnlabel", "headerimage",
    "jobstring", "verb", "gerundlabel",
    "labelmale", "labelfemale", "labelmechanoids",
    "beginletter", "beginletterdef", "helptext",
    "recoverymessage", "baseinspectline",
    "reportstring", "toil",
    "ingestcommandstring", "ingestreportstring",
    "offmessage", "arrivaltextenemy", "arrivaltextfriendly",
    "approachorderstring", "approachingreportstring",
    "arrivedletterlabel", "arrivedlettertext",
    "pawscangainroyaltitle",
    "discoveredlettertext", "discoveredlettertitle",
    "successfullyremovedhediffmessage",
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


KNOWN_ENUM_VALUES = {
    "childhood", "adulthood", "male", "female", "none",
    "industrial", "medieval", "neolithic", "spacer", "ultraspacer",
    "always", "never", "normal", "rare", "common",
    "light", "medium", "heavy",
    "melee", "ranged", "social", "animal", "trade",
    "cont",
    # Body structure enums
    "top", "bottom", "middle", "inside", "outside", "undefined",
    # Render / visual enums
    "base", "hair", "skin", "back", "front", "overhead",
    "cutout", "transparent", "mote", "basic", "advanced",
    "standard", "super", "humanlike", "sprint",
    "planks", "smooth", "rough",
    "slice", "blunt", "bullet", "stab",
    "gluttonous", "chemical", "idle",
    "deadly", "some", "great", "extreme",
    "food", "rest", "joy", "beauty", "comfort",
    "adult", "child", "baby",
    "glow",
    # Script / quest enums
    "fail", "success", "laborers",
}


def is_definitely_technical(text):
    t = text.strip()
    if not t:
        return True
    if t.lower() in KNOWN_ENUM_VALUES:
        return True
    # Pure numbers (int, float, with optional f suffix)
    if re.match(r"^-?\d+([.,]\d+)?f?$", t):
        return True
    if t.lower() in ("true", "false", "null", "none"):
        return True
    # UUID
    if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}", t, re.I):
        return True
    # Namespace (MyMod.MyClass.Method)
    if re.match(r"^[A-Z]\w+(\.[A-Z]\w+)+$", t):
        return True
    # File path (a/b/c.png)
    if re.match(r"^(\w+[/\\])+\w+(\.\w+)?$", t):
        return True
    if t.startswith("<") or t.startswith("{") or t.startswith("$"):
        return True
    # Script arrow syntax: "questDescription->some text"
    if "->" in t and not " " in t.split("->")[0]:
        return True
    # Coordinate tuples: (0.5, -0.3, 1.0) and ranges: (.60, Infinity)
    if re.match(r"^\(?-?[\d.]+,\s*-?[\d.]+(?:,\s*-?[\d.]+)*\)?$", t):
        return True
    if re.match(r"^\(?-?[\d.]+,\s*-?(?:[\d.]+|Infinity)\)?$", t, re.I):
        return True
    # Hex color
    if re.match(r"^#[0-9a-fA-F]{6,8}$", t):
        return True
    # Resolution (800x600)
    if re.match(r"^\d+x\d+$", t):
        return True
    # Only symbols / punctuation, no letters (◈, ▲, ▼▼, ., ...)
    if not re.search(r"[A-Za-zА-Яа-яёЁ]", t):
        return True
    # DefName-like stubs as descriptions: "YR_AP_SomeItem." or "SomePascalCase."
    if re.match(r"^[A-Z][A-Za-z0-9]*(_[A-Za-z0-9]+)+\.?$", t):
        return True
    # Single PascalCase identifier (no spaces): "Catharsis", "Gunsmithing"
    if re.match(r"^[A-Z][a-z]+([A-Z][a-z]+)+\d*$", t) and " " not in t:
        return True
    # Code identifiers: YRGroupA, YRgoodwillPenaltyPawn (prefix + camelCase)
    if re.match(r"^[A-Z]{2,}[a-z]\w*$", t) and " " not in t:
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
    if len(t.split()) == 2:
        return True
    return False


def is_translatable(tag_name, text, known_ids):
    t = text.strip()
    if not t:
        return False
    # KNOWN_TEXT_TAGS always win over blacklist (e.g. beginletterdef)
    low_tag = tag_name.lower()
    if low_tag in KNOWN_TEXT_TAGS:
        if is_definitely_technical(t):
            return False
        return True
    if is_blacklisted_tag(tag_name):
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
                        if " " not in val and re.match(r"^[A-Za-z_]\w*$", val):
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
                    translations[(file_path, original)] = translation
    except Exception:
        pass
    return translations


# ── Color Palette ─────────────────────────────────────────────────────────────

C = {
    "bg":       "#0d0d16",
    "surface":  "#16162a",
    "surface2": "#1e1e36",
    "surface3": "#252545",
    "border":   "#2e2e52",
    "accent":   "#7c3aed",
    "accent_h": "#6d28d9",
    "text":     "#e2e8f0",
    "muted":    "#8892a4",
    "success":  "#4ade80",
    "warning":  "#fbbf24",
    "error":    "#f87171",
    "info":     "#60a5fa",
    "log_bg":   "#0a0a10",
}


# ── i18n strings ──────────────────────────────────────────────────────────────

STRINGS = {
    "ru": {
        # UI
        "title":             "RimWorld Mod Translator",
        "mod_folder":        "Папка мода",
        "browse":            "Обзор…",
        "extra_tags":        "Доп. теги (через запятую)",
        "export":            "Экспорт в CSV",
        "import_":           "Импорт перевода",
        "save_cfg":          "Настройки",
        "clear":             "Очистить",
        "copy":              "Копировать",
        "select_all":        "Выделить всё",
        "lang_btn":          "EN",
        "log_title":         "Журнал",
        "ready":             "Готов к работе",
        # Messages
        "settings_saved":    "Настройки сохранены",
        "settings_error":    "Ошибка сохранения настроек: {0}",
        "settings_load_err": "Ошибка загрузки настроек: {0}",
        "folder_selected":   "Выбрана папка: {0}",
        "open_err":          "Не удалось открыть папку: {0}",
        "need_folder":       "Сначала выберите папку мода",
        "exporting":         "Экспорт…",
        "mod_folder_log":    "Папка мода: {0}",
        "found_xml":         "Найдено XML файлов: {0}",
        "no_xml":            "XML файлы не найдены",
        "pass1":             "Проход 1: сбор идентификаторов…",
        "found_ids":         "Идентификаторов: {0}",
        "force_tags_log":    "Принудительные теги: {0}",
        "found_prev":        "Предыдущих переводов: {0} (smart merge)",
        "pass2":             "Проход 2: извлечение текста…",
        "file_rows":         "  {0}: {1} строк",
        "files_progress":    "Файлов: {0}/{1}",
        "file_error":        "ОШИБКА: {0}: {1}",
        "total_rows":        "Всего строк: {0}",
        "new_rows":          "  Новых: {0}",
        "merged_rows":       "  Из прошлого: {0}",
        "unused_rows":       "  Устаревших (UNUSED): {0}",
        "files_with_text":   "Файлов с текстом: {0}/{1}",
        "saved_to":          "Файл сохранён: {0}",
        "done_exp":          "Готово. Строк: {0} (новых: {1})",
        "done_title":        "Готово",
        "export_done": (
            "Экспорт завершён!\n"
            "Файл: {output}\n"
            "Строк: {total} (новых: {new}, из прошлого: {merged})\n\n"
            "Статусы:\n"
            "  NEW  — нужен перевод\n"
            "  DONE — уже переведено\n"
            "  UNUSED — строка удалена из мода\n\n"
            'Google Sheets: =GOOGLETRANSLATE(D2;"auto";"ru")'
        ),
        "critical":          "Критическая ошибка: {0}",
        "export_err_status": "Ошибка при экспорте",
        "importing":         "Импорт…",
        "choose_csv":        "Выберите файл перевода",
        "loaded_tr":         "Загружено переводов: {0}",
        "skipped_unused":    "Пропущено устаревших: {0}",
        "no_tr":             "Нет переводов для импорта",
        "file_not_found":    "Файл не найден: {0}",
        "file_applied":      "  {0}: {1} переводов",
        "import_done":       "Импорт завершён! Файлов: {0}, переводов: {1}",
        "not_applied":       "Не удалось применить: {0}",
        "done_imp":          "Готово. Файлов: {0}, переводов: {1}",
        "import_done_msg": (
            "Импорт завершён!\n"
            "Обновлено файлов: {files}\n"
            "Применено переводов: {applied}"
        ),
        "import_err_status": "Ошибка при импорте",
        "parse_err":         "Ошибка парсинга: {0}: {1}",
        "read_err":          "Ошибка чтения: {0}: {1}",
        "xml_search_err":    "Ошибка поиска XML: {0}",
    },
    "en": {
        # UI
        "title":             "RimWorld Mod Translator",
        "mod_folder":        "Mod folder",
        "browse":            "Browse…",
        "extra_tags":        "Extra tags (comma-separated)",
        "export":            "Export to CSV",
        "import_":           "Import translation",
        "save_cfg":          "Settings",
        "clear":             "Clear",
        "copy":              "Copy",
        "select_all":        "Select all",
        "lang_btn":          "RU",
        "log_title":         "Log",
        "ready":             "Ready",
        # Messages
        "settings_saved":    "Settings saved",
        "settings_error":    "Error saving settings: {0}",
        "settings_load_err": "Error loading settings: {0}",
        "folder_selected":   "Folder selected: {0}",
        "open_err":          "Could not open folder: {0}",
        "need_folder":       "Please select a mod folder first",
        "exporting":         "Exporting…",
        "mod_folder_log":    "Mod folder: {0}",
        "found_xml":         "XML files found: {0}",
        "no_xml":            "No XML files found",
        "pass1":             "Pass 1: collecting identifiers…",
        "found_ids":         "Identifiers: {0}",
        "force_tags_log":    "Forced tags: {0}",
        "found_prev":        "Previous translations: {0} (smart merge)",
        "pass2":             "Pass 2: extracting translatable text…",
        "file_rows":         "  {0}: {1} rows",
        "files_progress":    "Files: {0}/{1}",
        "file_error":        "ERROR: {0}: {1}",
        "total_rows":        "Total rows: {0}",
        "new_rows":          "  New: {0}",
        "merged_rows":       "  From previous: {0}",
        "unused_rows":       "  Stale (UNUSED): {0}",
        "files_with_text":   "Files with text: {0}/{1}",
        "saved_to":          "File saved: {0}",
        "done_exp":          "Done. Rows: {0} (new: {1})",
        "done_title":        "Done",
        "export_done": (
            "Export complete!\n"
            "File: {output}\n"
            "Rows: {total} (new: {new}, previous: {merged})\n\n"
            "Status column:\n"
            "  NEW    — needs translation\n"
            "  DONE   — already translated\n"
            "  UNUSED — removed from mod\n\n"
            'Google Sheets: =GOOGLETRANSLATE(D2;"auto";"en")'
        ),
        "critical":          "Critical error: {0}",
        "export_err_status": "Export error",
        "importing":         "Importing…",
        "choose_csv":        "Choose translation file",
        "loaded_tr":         "Translations loaded: {0}",
        "skipped_unused":    "Stale rows skipped: {0}",
        "no_tr":             "No translations to import",
        "file_not_found":    "File not found: {0}",
        "file_applied":      "  {0}: {1} translations",
        "import_done":       "Import done! Files: {0}, translations: {1}",
        "not_applied":       "Could not apply: {0}",
        "done_imp":          "Done. Files: {0}, translations: {1}",
        "import_done_msg": (
            "Import complete!\n"
            "Files updated: {files}\n"
            "Translations applied: {applied}"
        ),
        "import_err_status": "Import error",
        "parse_err":         "Parse error: {0}: {1}",
        "read_err":          "Read error: {0}: {1}",
        "xml_search_err":    "XML search error: {0}",
    },
}


# ── Application ───────────────────────────────────────────────────────────────

class RimWorldTranslator:
    def __init__(self, root):
        self.root = root
        self.source_dir = tk.StringVar()
        self.force_tags = tk.StringVar()
        self.language = tk.StringVar(value="ru")
        self.settings_file = "translator_settings.json"

        self.load_settings()
        self._setup_fonts()
        self._apply_theme()
        self._build_ui()
        self._apply_dark_titlebar()

    # ── i18n helper ───────────────────────────────────────────────────────────

    def t(self, key, *args, **kwargs):
        template = STRINGS[self.language.get()].get(key, key)
        if kwargs:
            return template.format(*args, **kwargs)
        return template.format(*args) if args else template

    # ── Settings ──────────────────────────────────────────────────────────────

    def load_settings(self):
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    s = json.load(f)
                    self.force_tags.set(s.get("force_tags", ""))
                    self.language.set(s.get("language", "ru"))
        except Exception as e:
            print(f"Settings load error: {e}")

    def save_settings(self):
        try:
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(
                    {"force_tags": self.force_tags.get(),
                     "language": self.language.get()},
                    f, ensure_ascii=False, indent=2,
                )
            self.log(self.t("settings_saved"), "SUCCESS")
        except Exception as e:
            self.log(self.t("settings_error", e), "ERROR")

    # ── Fonts ─────────────────────────────────────────────────────────────────

    def _setup_fonts(self):
        import tkinter.font as tkfont
        families = set(tkfont.families())

        ui = next((f for f in ["Segoe UI", "SF Pro Display", "Ubuntu", "Helvetica Neue"]
                   if f in families), None)
        mono = next((f for f in ["Consolas", "JetBrains Mono", "SF Mono", "Ubuntu Mono", "Courier New"]
                     if f in families), None)

        self.font_ui       = (ui,   10)          if ui   else ("TkDefaultFont", 10)
        self.font_ui_b     = (ui,   10, "bold")  if ui   else ("TkDefaultFont", 10, "bold")
        self.font_title    = (ui,   14, "bold")  if ui   else ("TkDefaultFont", 13, "bold")
        self.font_small    = (ui,    9)          if ui   else ("TkDefaultFont",  9)
        self.font_mono     = (mono, 10)          if mono else ("TkFixedFont",   10)

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _apply_theme(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure(".",
            background=C["bg"], foreground=C["text"],
            fieldbackground=C["surface2"],
            bordercolor=C["border"],
            darkcolor=C["surface"], lightcolor=C["surface2"],
            troughcolor=C["surface"],
            selectbackground=C["accent"], selectforeground=C["text"],
            insertcolor=C["text"],
            font=self.font_ui,
        )

        style.configure("TFrame", background=C["bg"])

        style.configure("TLabel",
            background=C["bg"], foreground=C["text"], font=self.font_ui)
        style.configure("Title.TLabel",
            background=C["bg"], foreground=C["text"], font=self.font_title)

        style.configure("TEntry",
            fieldbackground=C["surface2"], foreground=C["text"],
            insertcolor=C["text"],
            bordercolor=C["border"],
            lightcolor=C["border"], darkcolor=C["border"],
            padding=(8, 7), relief="flat",
        )
        style.map("TEntry",
            bordercolor=[("focus", C["accent"])],
            lightcolor=[("focus", C["accent"])],
        )

        style.configure("Accent.TButton",
            background=C["accent"], foreground="white",
            bordercolor=C["accent"],
            lightcolor=C["accent"], darkcolor=C["accent_h"],
            focuscolor=C["accent"],
            relief="flat", padding=(14, 9), font=self.font_ui,
        )
        style.map("Accent.TButton",
            background=[("active", C["accent_h"]), ("pressed", C["accent_h"]),
                        ("disabled", C["surface3"])],
            foreground=[("disabled", C["muted"])],
        )

        style.configure("TButton",
            background=C["surface3"], foreground=C["text"],
            bordercolor=C["border"],
            lightcolor=C["border"], darkcolor=C["border"],
            focuscolor=C["surface2"],
            relief="flat", padding=(12, 9), font=self.font_ui,
        )
        style.map("TButton",
            background=[("active", C["surface2"]), ("pressed", C["surface"])],
            bordercolor=[("active", C["accent"])],
            lightcolor=[("active", C["accent"])],
        )

        style.configure("TProgressbar",
            background=C["accent"],
            troughcolor=C["surface2"],
            bordercolor=C["surface2"],
            lightcolor=C["accent"], darkcolor=C["accent_h"],
            thickness=5,
        )

        style.configure("TScrollbar",
            background=C["surface3"],
            troughcolor=C["log_bg"],
            bordercolor=C["log_bg"],
            arrowcolor=C["muted"],
            relief="flat", width=10,
        )
        style.map("TScrollbar",
            background=[("active", C["border"]), ("pressed", C["accent"])],
        )

    def _apply_dark_titlebar(self):
        if platform.system() != "Windows":
            return
        try:
            from ctypes import windll, c_int, byref, sizeof
            self.root.update()
            hwnd = windll.user32.GetParent(self.root.winfo_id())
            if not hwnd:
                hwnd = self.root.winfo_id()
            windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 20, byref(c_int(1)), sizeof(c_int)
            )
        except Exception:
            pass

    # ── UI Build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        s = STRINGS[self.language.get()]

        self.root.title(s["title"])
        self.root.configure(bg=C["bg"])
        self.root.geometry("940x730")
        self.root.minsize(700, 560)

        wrap = tk.Frame(self.root, bg=C["bg"])
        wrap.pack(fill=tk.BOTH, expand=True, padx=22, pady=20)

        # ── Header ────────────────────────────────────────────────────────────
        header = tk.Frame(wrap, bg=C["bg"])
        header.pack(fill=tk.X, pady=(0, 18))

        self._lbl_title = tk.Label(
            header, text=s["title"],
            bg=C["bg"], fg=C["text"], font=self.font_title,
        )
        self._lbl_title.pack(side=tk.LEFT)

        self._btn_lang = tk.Button(
            header, text=s["lang_btn"],
            bg=C["surface3"], fg=C["muted"],
            font=self.font_small, relief="flat",
            padx=10, pady=4, cursor="hand2",
            activebackground=C["surface2"], activeforeground=C["text"],
            command=self._toggle_language,
        )
        self._btn_lang.pack(side=tk.RIGHT)

        # ── Folder card ───────────────────────────────────────────────────────
        fc = self._card(wrap)
        fc.pack(fill=tk.X, pady=(0, 8))

        self._lbl_folder = tk.Label(
            fc, text=s["mod_folder"],
            bg=C["surface"], fg=C["muted"], font=self.font_small,
        )
        self._lbl_folder.pack(anchor=tk.W, pady=(0, 5))

        row = tk.Frame(fc, bg=C["surface"])
        row.pack(fill=tk.X)

        self._entry_folder = ttk.Entry(row, textvariable=self.source_dir)
        self._entry_folder.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._btn_browse = ttk.Button(
            row, text=s["browse"], command=self.browse_directory,
        )
        self._btn_browse.pack(side=tk.LEFT, padx=(6, 0))

        self._btn_open = ttk.Button(
            row, text="📁", command=self.open_directory, width=3,
        )
        self._btn_open.pack(side=tk.LEFT, padx=(4, 0))

        # ── Tags card ─────────────────────────────────────────────────────────
        tc = self._card(wrap)
        tc.pack(fill=tk.X, pady=(0, 14))

        self._lbl_tags = tk.Label(
            tc, text=s["extra_tags"],
            bg=C["surface"], fg=C["muted"], font=self.font_small,
        )
        self._lbl_tags.pack(anchor=tk.W, pady=(0, 5))

        self._entry_tags = ttk.Entry(tc, textvariable=self.force_tags)
        self._entry_tags.pack(fill=tk.X)

        # ── Action buttons ────────────────────────────────────────────────────
        actions = tk.Frame(wrap, bg=C["bg"])
        actions.pack(fill=tk.X, pady=(0, 14))

        self._btn_export = ttk.Button(
            actions, text=s["export"],
            style="Accent.TButton", command=self.export_text,
        )
        self._btn_export.pack(side=tk.LEFT, padx=(0, 8))

        self._btn_import = ttk.Button(
            actions, text=s["import_"],
            style="Accent.TButton", command=self.import_translation,
        )
        self._btn_import.pack(side=tk.LEFT, padx=(0, 8))

        self._btn_save = ttk.Button(
            actions, text=s["save_cfg"], command=self.save_settings,
        )
        self._btn_save.pack(side=tk.LEFT)

        # ── Progress bar ──────────────────────────────────────────────────────
        self.progress = ttk.Progressbar(wrap, mode="determinate")
        self.progress.pack(fill=tk.X, pady=(0, 14))

        # ── Log header ────────────────────────────────────────────────────────
        lh = tk.Frame(wrap, bg=C["bg"])
        lh.pack(fill=tk.X, pady=(0, 5))

        self._lbl_log = tk.Label(
            lh, text=s["log_title"],
            bg=C["bg"], fg=C["muted"], font=self.font_small,
        )
        self._lbl_log.pack(side=tk.LEFT)

        self._btn_clear = tk.Button(
            lh, text=s["clear"],
            bg=C["bg"], fg=C["muted"],
            font=self.font_small, relief="flat", cursor="hand2",
            activebackground=C["bg"], activeforeground=C["text"],
            command=self.clear_log,
        )
        self._btn_clear.pack(side=tk.RIGHT)

        # ── Log text ──────────────────────────────────────────────────────────
        log_border = tk.Frame(
            wrap, bg=C["surface2"],
            highlightbackground=C["border"], highlightthickness=1,
        )
        log_border.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.log_text = tk.Text(
            log_border,
            bg=C["log_bg"], fg=C["text"],
            insertbackground=C["text"],
            selectbackground=C["accent"], selectforeground="white",
            font=self.font_mono,
            wrap=tk.WORD,
            padx=12, pady=10,
            relief="flat", borderwidth=0,
            cursor="arrow",
        )
        scrollbar = ttk.Scrollbar(log_border, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.log_text.tag_configure("INFO",    foreground=C["text"])
        self.log_text.tag_configure("SUCCESS", foreground=C["success"])
        self.log_text.tag_configure("WARNING", foreground=C["warning"])
        self.log_text.tag_configure("ERROR",   foreground=C["error"])
        self.log_text.tag_configure("TS",      foreground=C["muted"])

        self._build_context_menu()

        # ── Status bar ────────────────────────────────────────────────────────
        self.status_var = tk.StringVar(value=s["ready"])
        sb = tk.Frame(wrap, bg=C["surface"], height=28)
        sb.pack(fill=tk.X)
        sb.pack_propagate(False)
        self._lbl_status = tk.Label(
            sb, textvariable=self.status_var,
            bg=C["surface"], fg=C["muted"],
            font=self.font_small, anchor=tk.W, padx=10,
        )
        self._lbl_status.pack(fill=tk.BOTH, expand=True)

    def _card(self, parent):
        return tk.Frame(
            parent, bg=C["surface"],
            highlightbackground=C["border"], highlightthickness=1,
            padx=14, pady=12,
        )

    # ── Language ──────────────────────────────────────────────────────────────

    def _toggle_language(self):
        self.language.set("en" if self.language.get() == "ru" else "ru")
        self._refresh_ui_text()

    def _refresh_ui_text(self):
        s = STRINGS[self.language.get()]
        self.root.title(s["title"])
        self._lbl_title.config(text=s["title"])
        self._btn_lang.config(text=s["lang_btn"])
        self._lbl_folder.config(text=s["mod_folder"])
        self._btn_browse.config(text=s["browse"])
        self._lbl_tags.config(text=s["extra_tags"])
        self._btn_export.config(text=s["export"])
        self._btn_import.config(text=s["import_"])
        self._btn_save.config(text=s["save_cfg"])
        self._lbl_log.config(text=s["log_title"])
        self._btn_clear.config(text=s["clear"])
        self.status_var.set(s["ready"])
        self.context_menu.entryconfigure(0, label=s["copy"])
        self.context_menu.entryconfigure(1, label=s["select_all"])
        self.context_menu.entryconfigure(3, label=s["clear"])

    # ── Context menu ──────────────────────────────────────────────────────────

    def _build_context_menu(self):
        s = STRINGS[self.language.get()]
        self.context_menu = tk.Menu(
            self.log_text, tearoff=0,
            bg=C["surface3"], fg=C["text"],
            activebackground=C["accent"], activeforeground="white",
        )
        self.context_menu.add_command(label=s["copy"],       command=self._copy_log)
        self.context_menu.add_command(label=s["select_all"], command=self._select_all_log)
        self.context_menu.add_separator()
        self.context_menu.add_command(label=s["clear"],      command=self.clear_log)
        self.log_text.bind("<Button-3>", self._show_context_menu)

    def _show_context_menu(self, event):
        try:
            self.context_menu.post(event.x_root, event.y_root)
        except Exception:
            pass

    def _copy_log(self):
        try:
            txt = self.log_text.get(tk.SEL_FIRST, tk.SEL_LAST)
            self.root.clipboard_clear()
            self.root.clipboard_append(txt)
        except tk.TclError:
            pass

    def _select_all_log(self):
        self.log_text.tag_add(tk.SEL, "1.0", tk.END)
        self.log_text.mark_set(tk.INSERT, "1.0")
        self.log_text.see(tk.INSERT)

    # ── Directory ─────────────────────────────────────────────────────────────

    def browse_directory(self):
        d = filedialog.askdirectory(title=self.t("mod_folder"))
        if d:
            self.source_dir.set(d)
            self.log(self.t("folder_selected", d))

    def open_directory(self):
        d = self.source_dir.get()
        if not d or not os.path.exists(d):
            messagebox.showwarning("", self.t("need_folder"))
            return
        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(d)
            elif system == "Darwin":
                subprocess.Popen(["open", d])
            else:
                subprocess.Popen(["xdg-open", d])
        except Exception as e:
            self.log(self.t("open_err", e), "ERROR")

    # ── Log ───────────────────────────────────────────────────────────────────

    def log(self, message, level="INFO"):
        try:
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_text.insert(tk.END, f"[{ts}]", "TS")
            self.log_text.insert(tk.END, f" {message}\n", level)
            self.log_text.see(tk.END)
            self.root.update_idletasks()
        except Exception:
            pass

    def clear_log(self):
        self.log_text.delete("1.0", tk.END)

    def update_progress(self, value, maximum=100):
        self.progress["value"] = value
        self.progress["maximum"] = maximum
        self.root.update_idletasks()

    def get_force_tags(self):
        return {t.strip().lower() for t in self.force_tags.get().split(",") if t.strip()}

    # ── XML helpers ───────────────────────────────────────────────────────────

    def find_xml_files(self, directory):
        xml_files = []
        skip = {".git", ".vs", "bin", "obj", "__pycache__"}
        skip_files = {"loadfolders.xml", "about.xml", "manifest.xml", "publishedfileid.xml"}
        try:
            for root_dir, dirs, files in os.walk(directory):
                if any(s in root_dir.lower() for s in skip):
                    continue
                for f in files:
                    if f.lower().endswith(".xml") and f.lower() not in skip_files:
                        xml_files.append(os.path.join(root_dir, f))
        except Exception as e:
            self.log(self.t("xml_search_err", e), "ERROR")
        return xml_files

    def indent_xml(self, elem, level=0):
        """Indent XML tree in-place. Fixes last-child tail to close parent correctly."""
        i = "\n" + level * "  "
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
            for child in elem:
                self.indent_xml(child, level + 1)
            # Fix last child's tail so the parent's closing tag indents correctly
            last_child = list(elem)[-1]
            if not last_child.tail or not last_child.tail.strip():
                last_child.tail = i
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = i

    # ── Export ────────────────────────────────────────────────────────────────

    def export_text(self):
        if not self.source_dir.get() or not os.path.exists(self.source_dir.get()):
            messagebox.showerror("", self.t("need_folder"))
            return

        self.clear_log()
        self.status_var.set(self.t("exporting"))
        self.update_progress(0)

        try:
            self.log(self.t("mod_folder_log", self.source_dir.get()))

            xml_files = self.find_xml_files(self.source_dir.get())
            self.log(self.t("found_xml", len(xml_files)))

            if not xml_files:
                self.log(self.t("no_xml"), "WARNING")
                messagebox.showwarning("", self.t("no_xml"))
                return

            self.log(self.t("pass1"))
            self.status_var.set(self.t("pass1"))
            known_ids = collect_identifiers(xml_files)
            self.log(self.t("found_ids", len(known_ids)))

            force = self.get_force_tags()
            if force:
                self.log(self.t("force_tags_log", ", ".join(force)))

            output_file = "translations.csv"
            old_translations = load_existing_translations(output_file)
            if old_translations:
                self.log(self.t("found_prev", len(old_translations)), "SUCCESS")

            self.log(self.t("pass2"))
            total_units = new_units = merged_units = processed_files = 0
            seen_keys = set()

            with open(output_file, "w", encoding="utf-8-sig", newline="") as csvfile:
                writer = csv.writer(csvfile, delimiter=",", quotechar='"',
                                    quoting=csv.QUOTE_MINIMAL)
                writer.writerow(["File", "Tag", "XPath", "Original Text",
                                 "Translation", "Status", "Placeholders"])

                for i, xml_file in enumerate(xml_files):
                    try:
                        rel = os.path.relpath(xml_file, self.source_dir.get())
                        ft, fn, fm = self.extract_from_file(
                            xml_file, rel, known_ids, force,
                            old_translations, seen_keys, writer,
                        )
                        total_units   += ft
                        new_units     += fn
                        merged_units  += fm
                        if ft > 0:
                            processed_files += 1
                            self.log(self.t("file_rows", rel, ft))
                        self.update_progress((i + 1) / len(xml_files) * 100)
                        self.status_var.set(self.t("files_progress", i + 1, len(xml_files)))
                    except Exception as e:
                        self.log(self.t("file_error", xml_file, e), "ERROR")

                unused_count = 0
                for (fp, orig), tr in old_translations.items():
                    if (fp, orig) not in seen_keys:
                        writer.writerow([fp, "", "", orig, tr, "UNUSED", ""])
                        unused_count += 1

            self.log("—" * 40)
            self.log(self.t("total_rows", total_units), "SUCCESS")
            self.log(self.t("new_rows", new_units))
            self.log(self.t("merged_rows", merged_units))
            if unused_count:
                self.log(self.t("unused_rows", unused_count), "WARNING")
            self.log(self.t("files_with_text", processed_files, len(xml_files)))
            self.log(self.t("saved_to", output_file), "SUCCESS")
            self.status_var.set(self.t("done_exp", total_units, new_units))
            self.update_progress(0)

            messagebox.showinfo(
                self.t("done_title"),
                self.t("export_done",
                       output=output_file, total=total_units,
                       new=new_units, merged=merged_units),
            )
        except Exception as e:
            self.log(self.t("critical", e), "ERROR")
            messagebox.showerror("", str(e))
            self.status_var.set(self.t("export_err_status"))
            self.update_progress(0)

    def extract_from_file(self, xml_file, relative_path, known_ids,
                          force_tags, old_translations, seen_keys, csv_writer):
        total = new = merged = 0
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
        except ET.ParseError as e:
            self.log(self.t("parse_err", relative_path, e), "ERROR")
            return 0, 0, 0
        except Exception as e:
            self.log(self.t("read_err", relative_path, e), "ERROR")
            return 0, 0, 0

        for elem in root.iter():
            if not isinstance(elem.tag, str):
                continue
            if not elem.text or not elem.text.strip():
                continue

            tag_name = elem.tag
            text = elem.text.strip()
            forced = tag_name.lower() in force_tags

            if forced and not is_definitely_technical(text):
                pass
            elif not is_translatable(tag_name, text, known_ids):
                continue

            key = (relative_path, text)
            seen_keys.add(key)
            masked_text, map_str = mask_placeholders(text)
            old_tr = old_translations.get(key, "")

            if old_tr:
                masked_tr, _ = mask_placeholders(old_tr)
                status = "DONE"
                merged += 1
            else:
                masked_tr = ""
                status = "NEW"
                new += 1

            csv_writer.writerow(
                [relative_path, tag_name, f"//{tag_name}",
                 masked_text, masked_tr, status, map_str]
            )
            total += 1

        return total, new, merged

    # ── Import ────────────────────────────────────────────────────────────────

    def import_translation(self):
        if not self.source_dir.get() or not os.path.exists(self.source_dir.get()):
            messagebox.showerror("", self.t("need_folder"))
            return

        csv_file = filedialog.askopenfilename(
            title=self.t("choose_csv"),
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not csv_file:
            return

        self.clear_log()
        self.status_var.set(self.t("importing"))
        self.update_progress(0)

        try:
            self.log(f"CSV: {csv_file}")

            by_file = defaultdict(list)
            total_rows = skipped_unused = 0

            with open(csv_file, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if (row.get("Status") or "").strip().upper() == "UNUSED":
                        skipped_unused += 1
                        continue
                    fp  = (row.get("File") or "").strip()
                    tag = (row.get("Tag")  or "").strip()
                    orig = row.get("Original Text") or ""
                    tr   = row.get("Translation")   or ""
                    ms   = row.get("Placeholders")  or ""
                    if not fp or not tag or not tr.strip():
                        continue
                    by_file[fp].append((
                        tag,
                        unmask_placeholders(orig, ms),
                        unmask_placeholders(tr, ms),
                    ))
                    total_rows += 1

            self.log(self.t("loaded_tr", total_rows))
            if skipped_unused:
                self.log(self.t("skipped_unused", skipped_unused))

            if not by_file:
                self.log(self.t("no_tr"), "WARNING")
                messagebox.showwarning("", self.t("no_tr"))
                return

            updated_files = applied_units = skipped_units = 0
            items_list = list(by_file.items())

            for i, (fp, items) in enumerate(items_list):
                full_path = os.path.join(self.source_dir.get(), fp)
                if not os.path.exists(full_path):
                    self.log(self.t("file_not_found", fp), "WARNING")
                    skipped_units += len(items)
                    continue
                try:
                    applied, skipped = self.apply_translations_to_file(full_path, items)
                    applied_units += applied
                    skipped_units += skipped
                    if applied > 0:
                        updated_files += 1
                        self.log(self.t("file_applied", fp, applied))
                except Exception as e:
                    self.log(self.t("file_error", fp, e), "ERROR")
                    skipped_units += len(items)

                self.update_progress((i + 1) / len(items_list) * 100)
                self.status_var.set(self.t("files_progress", i + 1, len(items_list)))

            self.log("—" * 40)
            self.log(self.t("import_done", updated_files, applied_units), "SUCCESS")
            if skipped_units:
                self.log(self.t("not_applied", skipped_units), "WARNING")
            self.status_var.set(self.t("done_imp", updated_files, applied_units))
            self.update_progress(0)

            messagebox.showinfo(
                self.t("done_title"),
                self.t("import_done_msg", files=updated_files, applied=applied_units),
            )
        except Exception as e:
            self.log(self.t("critical", e), "ERROR")
            messagebox.showerror("", str(e))
            self.status_var.set(self.t("import_err_status"))
            self.update_progress(0)

    def apply_translations_to_file(self, xml_file, items):
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
        except ET.ParseError as e:
            self.log(self.t("parse_err", xml_file, e), "ERROR")
            return 0, len(items)

        pending = defaultdict(list)
        for tag, orig, tr in items:
            pending[(tag, orig)].append(tr)

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


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    try:
        root = tk.Tk()
        RimWorldTranslator(root)
        root.mainloop()
    except Exception as e:
        print(f"Fatal error: {e}")
        input("Press Enter to exit…")


if __name__ == "__main__":
    main()
