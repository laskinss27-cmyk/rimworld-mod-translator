# RimWorld Mod Translator v3.0

Tool for translating RimWorld mods into any language using Google Sheets and the `GOOGLETRANSLATE` formula.

Инструмент для перевода модов RimWorld на любой язык с помощью Google Sheets и формулы `GOOGLETRANSLATE`.

---

## Quick Start / Быстрый старт

1. Download `RimWorldTranslator.exe` from [Releases](https://github.com/laskinss27-cmyk/rimworld-mod-translator/releases)
2. Run it — no Python or dependencies needed
3. Select the **root folder** of the mod → Export → Translate → Import

---

## ⚠️ Important Notes / Важные замечания

### Always point to the mod root folder / Всегда указывайте корневую папку мода

```
✅ Mods/2844129100_yuran_race/
❌ Mods/2844129100_yuran_race/1.6/Defs/
```

The program recursively scans all subfolders (`1.3/`, `1.4/`, `1.5/`, `Compatibility/`, etc.). If you point to a subfolder, files outside it will be missed.

Программа рекурсивно сканирует все подпапки (`1.3/`, `1.4/`, `1.5/`, `Compatibility/` и т.д.). Если указать подпапку — файлы за её пределами будут пропущены.

### Always review the CSV before translating / Всегда проверяйте CSV перед переводом

The program uses smart heuristics to separate translatable text from technical data, but **no filter is 100% perfect** — especially with mods that use many custom tags.

Before translating, scan the CSV and check:
- Are there any numbers, enum values, or code-like strings? → Delete those rows
- Is there text that looks like an identifier (PascalCase, paths)? → Delete those rows
- Is there real text that was missed? → Add the tag name to "Extra tags" field and re-export

Программа использует эвристики для отделения текста от технических данных, но **ни один фильтр не идеален на 100%** — особенно с модами, которые используют много кастомных тегов.

Перед переводом просмотрите CSV и проверьте:
- Есть ли числа, enum-значения, строки похожие на код? → Удалите эти строки
- Есть ли текст, похожий на идентификатор (PascalCase, пути)? → Удалите эти строки
- Есть ли пропущенный текст? → Добавьте имя тега в поле «Доп. теги» и пересканируйте

### Do not delete the Languages/ folder / Не удаляйте папку Languages/

The `Languages/` folder contains not only translations but also **name lists**, **grammar rules**, and **string files** required by the mod. Deleting it causes errors like `No string files for Name/...` and `Grammar unresolvable`.

Папка `Languages/` содержит не только переводы, но и **списки имён**, **правила грамматики** и **строковые файлы**, необходимые моду. Её удаление вызывает ошибки вида `No string files for Name/...` и `Grammar unresolvable`.

---

## How the filter works / Как работает фильтрация

Three layers of analysis:

### Layer 1: Tag blacklist / Чёрный список тегов

Tags that **never** contain translatable text:

```
defName, parentName, thingClass, workerClass, texPath, soundDef, shaderType,
slot, category, capacity, outcome, storeAs, ...
```

Patterns: any tag ending in `Class`, `Path`, `Def`, `Defs`, `Color`, `Size`, `Offset`, or starting with `sound`.

### Layer 2: Value analysis / Анализ значений

| Value | Decision | Reason |
|-------|----------|--------|
| `A wooden table for eating.` | ✅ Translate | Multiple words, ends with period |
| `WoodenTable` | ❌ Skip | PascalCase — identifier |
| `Things/Building/Table` | ❌ Skip | File path |
| `true` / `false` | ❌ Skip | Boolean |
| `0.85` | ❌ Skip | Number |
| `#FF5500` | ❌ Skip | Color code |
| `Childhood` / `Fail` / `Success` | ❌ Skip | Known enum value |
| `(0.34, 0.5, -0.1)` | ❌ Skip | Coordinate tuple |
| `$($var * 60200)` | ❌ Skip | Code expression |
| `Fire` | Depends | Cross-checked against defNames |

### Layer 3: Cross-reference / Перекрёстная проверка

Before extracting text, the program collects all `defName` values and `*Def` references across the mod. If a value matches a known identifier — it is **not translated**, even if it looks like a normal word.

---

## Workflow

### 1. Export / Экспорт

1. Select the **root folder** of the mod
2. Click "Export to CSV"
3. **Review the CSV** — remove any false positives
4. The file `translations.csv` is created next to the program

### 2. Translate in Google Sheets / Перевод в Google Sheets

1. Open `translations.csv` in Google Sheets (File → Import → Upload)
2. Filter by **Status** = `NEW`
3. In the **Translation** column (E), enter the formula:
   ```
   =GOOGLETRANSLATE(D2; "auto"; "ru")
   ```
4. Drag the formula to all NEW rows
5. Copy the Translation column → Paste as **values only** (Ctrl+Shift+V)
6. Download as CSV (File → Download → CSV)

Supported languages: any supported by Google Translate. Replace `"ru"` with the desired code (`"de"`, `"fr"`, `"zh"`, `"ja"`, `"ko"`, `"uk"`, etc.).

### 3. Import / Импорт

1. Click "Import translation"
2. Select the translated CSV
3. The program inserts translations back into the mod's XML files

Rows with status `UNUSED` are automatically skipped during import.

---

## Smart Merge

When re-exporting (e.g., after a mod update):

- **NEW** — new string, needs translation
- **DONE** — already translated, translation is preserved
- **UNUSED** — was in previous translation but no longer in the mod. Kept in CSV just in case, skipped on import

**Updating a mod does not destroy your work.** Translated strings are preserved, only new ones need translation.

---

## Extra tags / Дополнительные теги

The "Extra tags" field lets you force-include tags the program didn't recognize as text. Comma-separated, e.g.: `customTag, myModLabel`. Use only if the program missed translatable text.

---

## Placeholders / Плейсхолдеры

The program automatically protects placeholders like `{pawn}`, `{0}`, `[PAWN_nameDef]`, `[PAWN_pronoun]` from being mangled by translation. They are masked before export and restored on import.

---

## Limitations / Ограничения

- **Translation quality** depends on Google Translate. For RimWorld context (medieval, sci-fi, specific terminology), machine translation may be inaccurate. Manual review is recommended.
- **Nested markup** — if a tag contains child elements (`<text>Before <b>war</b></text>`), only the text before the first child is extracted.
- **DLL strings** — text inside compiled assemblies (.dll) is not extracted.
- **Edge cases** — single-word values in custom tags may occasionally be included or missed. The "Extra tags" field and manual CSV review solve this.

---

## Installation / Установка

### Option 1: Download exe (recommended)

Download `RimWorldTranslator.exe` from [Releases](https://github.com/laskinss27-cmyk/rimworld-mod-translator/releases). No dependencies needed.

### Option 2: Run from source

Requirements: Python 3.6+, Tkinter (included with Python).

```bash
python rimworld_translator.py
```

---

## License / Лицензия

MIT
