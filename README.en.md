# RimWorld Mod Translator

[Русская документация](README.md)

A desktop tool for translating RimWorld mods. It uses heuristics to extract text from XML into CSV, then builds a **separate translation mod** from your translations. The recommended build mode leaves the source mod unchanged. Review the extracted rows before translating.

The Windows EXE requires no Python installation or XML editing. The workflow is: export → translate in a spreadsheet → build a translation mod.

![platform](https://img.shields.io/badge/platform-Windows-blue)
![python](https://img.shields.io/badge/python-3.6%2B-yellow)
![license](https://img.shields.io/badge/license-MIT-green)
![release](https://img.shields.io/github/v/release/laskinss27-cmyk/rimworld-mod-translator)

## Features

- **Text filtering:** tag rules, value checks and identifier cross-references help exclude technical data. Known text tags and English Keyed have exceptions, so review the CSV.
- **Separate translation mod:** generates `Languages/<language>/DefInjected` and `Keyed` without rewriting the original XML.
- **Smart Merge:** reuses saved translations when you export an updated mod.
- **Placeholder protection:** masks inserts such as `{0}`, `{pawn}`, `{PAWN_gender ? his : her}` and `[PAWN_nameDef]`. The separate mod builder skips translations with mismatched recognized placeholders.
- **Extra tags:** extends extraction for custom tags, subject to technical-value checks.
- **RU / EN interface:** dark theme, with a Settings button to save the interface language and extra tags.
- **Standalone Windows EXE:** no runtime packages to install.
- **Legacy Edit original mode:** edits source XML after making backups.

## Installation

### Windows EXE

1. Download `RimWorldTranslator.exe` from [Releases](https://github.com/laskinss27-cmyk/rimworld-mod-translator/releases).
2. If the release includes `RimWorldTranslator.exe.sha256`, use it to verify the EXE checksum.
3. Run the EXE. Windows may show a SmartScreen prompt for an unsigned executable.

### Run from source

The project declares **Python 3.6+** support and requires **Tkinter**, normally included with Python on Windows. GitHub Actions builds and tests with **Python 3.12**; use that version to reproduce the release build. Older Python versions are not all tested automatically.

```bash
python rimworld_translator.py
```

No third-party runtime packages are required. PyInstaller is only needed to build an EXE.

### Build an EXE

With Python 3.12:

```bash
python -m pip install pyinstaller==6.16.0
python -m unittest -v
python -m PyInstaller --noconfirm --clean --onefile --windowed --name RimWorldTranslator rimworld_translator.py
```

The result is `dist/RimWorldTranslator.exe`. The GitHub Actions workflow runs on `v*` tags or manual dispatch, tests the code, and uploads the EXE and checksum as a workflow artifact. For a tag run it also uploads them to an **existing GitHub Release** for that tag; the workflow does not create the release itself.

## Interface

| Control | Purpose |
|---|---|
| **Mod folder** | Select the root of the source mod. The folder icon opens it in Explorer. |
| **Extra tags** | Comma-separated tag names to extend extraction, subject to technical-value checks. |
| **Export to CSV** | Writes `translations.csv` in the current working directory. |
| **Build translation mod** | Builds a separate mod from a translated CSV. |
| **Edit original** | Edits source XML after backing it up. |
| **Settings** | Saves the interface language and extra tags to `translator_settings.json` in the current working directory. |
| **RU / EN** | Switches the interface language. |
| Log and status | Displays progress, errors and warnings. |

## Quick start

1. Run the application and select the **root folder** of a mod.
2. Click **Export to CSV**.
3. Review the CSV and remove clearly technical rows.
4. Translate the `Translation` column manually or in Google Sheets.
5. Click **Build translation mod**, select the translated CSV, enter the RimWorld language folder and target game version, then choose an output directory.
6. Read `Generation report.txt` in the generated package.
7. Copy the generated folder into RimWorld's `Mods` directory and enable it **after** the original mod.

Select the mod root, not a nested `Defs` directory:

```text
Correct:   Mods/2844129100_yuran_race/
Incorrect: Mods/2844129100_yuran_race/1.6/Defs/
```

Typical Windows locations:

- Steam Workshop: `Steam\steamapps\workshop\content\294100\<id>`
- Local mods: `RimWorld\Mods\`

## Export and CSV

Export recursively finds XML outside excluded directories and service manifests, collects identifiers, applies text filters, masks placeholders, and merges saved translations.

The output is always named **`translations.csv` in the current working directory**. This is the directory from which the program was launched; for a shortcut, check its “Start in” field. It can differ from the EXE directory. Export reads the existing file and then overwrites it. Before exporting again, save your translated CSV under this name and keep a separate copy for each mod.

CSV export uses UTF-8 with BOM (`utf-8-sig`).

| Column | Meaning |
|---|---|
| `File` | XML path relative to the source mod root. |
| `Tag` | XML tag name, such as `label`, `description` or a Keyed key. |
| `XPath` | A hint such as `//label`, not a unique XPath used for matching. |
| `Original Text` | Source text with placeholders masked as `__RWPH_0__`, etc. |
| `Translation` | Your translation; already populated for `DONE` rows. |
| `Status` | `NEW`, `DONE` or `UNUSED`. |
| `Placeholders` | Token mapping, such as `__RWPH_0__={0}`. Do not edit it. |

- **NEW:** no nonempty saved translation was found. The row may be new or previously untranslated.
- **DONE:** a saved translation was found. This is not a quality or placeholder-validation result.
- **UNUSED:** a previously translated row no longer appears in the extraction. Its text may have changed, been removed, or been excluded by filtering. The saved translation remains in the CSV, but build and import skip the row. Old untranslated rows are not retained.

## Translate in Google Sheets

1. Import `translations.csv` using File → Import.
2. Filter `Status` to `NEW`.
3. Fill `Translation` in the first visible untranslated row. For row 2, enter this in `E2`:

   ```text
   =GOOGLETRANSLATE(D2; "auto"; "ru")
   ```

   Use the same row number for the original and translation cells. Replace `ru` with your target language code. If your spreadsheet locale uses commas between arguments, replace `;` with `,`.

4. Fill only `NEW` rows with empty translations. Preserve existing `DONE` translations. For bulk translation, you can copy new rows to a separate sheet and return the results to their original CSV rows.
5. Wait for translation results. Optionally freeze them by copying and pasting **values only** (`Ctrl+Shift+V`).
6. Check that placeholder tokens such as `__RWPH_0__` remain intact.
7. Download as CSV.

Machine translation often misses RimWorld terminology. Review item names and game messages before publishing.

## Build a translation mod

The builder asks for:

1. The translated CSV.
2. A RimWorld language folder name, such as `Russian`, `German`, `French`, `Spanish`, `ChineseSimplified`, `Japanese`, `Korean`, `Polish`, `PortugueseBrazilian` or `Ukrainian`.
3. A target game version, such as `1.6`. Rows in paths for other versions are excluded; common, unversioned paths remain included.
4. An output parent directory.

The application creates `<ModName>_<Language>_Translation`. If that directory already exists, it appends a timestamp.

```text
Example Mod_Russian_Translation/
├── About/About.xml
├── Languages/Russian/DefInjected/ThingDef/Things.xml
├── Languages/Russian/Keyed/UI.xml
└── Generation report.txt
```

If the source `About/About.xml` contains a `packageId`, the generated metadata declares the original mod as a dependency and adds `loadAfter`. Otherwise, the report warns that the dependency needs manual checking. The source mod is not rewritten.

Generated language XML includes comments with the original text. Read **`Generation report.txt`** for generated entry counts, unmatched CSV rows, placeholder mismatches, unnamed Defs, repeated tags, duplicate keys and missing package metadata.

## Smart Merge after an update

1. Back up the mod's CSV and put its translated version in the working directory as `translations.csv`.
2. Select the updated mod and export again.
3. Previously translated phrases become `DONE`; phrases without a saved translation become `NEW`.
4. Previously translated phrases missing from the extraction become `UNUSED`.

Merge matches **relative file path + original text**, with placeholders restored. A changed source phrase or file path needs a new translation. Tag names are not part of this key: identical source phrases in the same file share one saved translation.

## Filtering rules

No heuristic filter is perfect, especially with custom mod tags.

### Tag rules

Normal extraction excludes technical tags such as `defName`, `parentName`, `thingClass`, `texPath`, `shaderType`, `slot`, `category`, `capacity`, `outcome` and `storeAs`.

It also excludes suffixes `Class`, `Path`, `Def`, `Defs`, `Color`, `Size`, `Offset`, `Shader`, `Type`, `Tag`, `Channel`, and prefixes `sound`, `render`, `default`.

Known text tags, including `label`, `description`, `letterText`, `jobString` and `beginLetterDef`, take priority over the blacklist, subject to their technical-value checks.

### Value rules

These examples apply to ordinary tags outside the blacklist, known text tags and forced inclusion:

| Value | Normal result |
|---|---|
| `A wooden table for eating.` | Include as a phrase. |
| `WoodenTable` | Skip as PascalCase. |
| `Things/Building/Table` | Skip as a path. |
| `true`, `false`, `0.85` | Skip as technical values. |
| `#FF5500` | Skip as a color. |
| `Childhood`, `Fail`, `Success` | Skip as known enum values. |
| `(0.34, 0.5, -0.1)` | Skip as coordinates. |
| `$($var * 60200)` | Skip as an expression. |
| Three or more words, a line break, or length over 60 | Include after technical checks. |

Known text tags allow enum words such as `Finish` and `Reverse`, which may be button labels. They also bypass ordinary PascalCase, color and known-identifier checks. English Keyed text bypasses these filters entirely, so technical values can still reach the CSV.

### Identifier cross-references

Before extraction, the program collects `defName` values, identifier-like `*Def` / `*Defs` values and some `li` values. In normal extraction it rejects matching values **after** checking for obvious phrases. Known text tags, English Keyed and forced values that pass the technical filter bypass this check. For example, `Fire` may be excluded in a custom tag but retained in `label`.

### Extra tags

Enter comma-separated, case-insensitive names, for example `customTag, myModLabel`.

Forced inclusion only applies when the value passes `is_definitely_technical`. That check rejects numbers, paths, UUIDs, known enums, PascalCase, colors and other technical forms. If it fails, normal tag rules still apply. Extra tags cannot guarantee inclusion of every value.

## Placeholders

Export masks recognized inserts with tokens such as `__RWPH_0__`. The `Placeholders` column stores the mapping. Build and import restore the original inserts.

Recognized forms include `{0}`, `{pawn}`, `{PAWN_nameDef}`, `{PAWN_gender ? his : her}`, `[PAWN_pronoun]` and `[PAWN_nameDef]`.

- Preserve the tokens and do not translate the contents of the original inserts.
- The **separate mod builder** compares recognized placeholders and their counts after restoration. It skips mismatches and records `Placeholder mismatch` in the report.
- **Edit original** restores tokens but does not perform this mismatch check.
- Nested braces and unusual placeholder formats may need manual review.

## Scanning scope and limitations

The exporter scans XML recursively across the mod, including `Defs`, version directories and compatibility directories. Within `Languages`, it only includes `Languages/English/Keyed`.

It excludes `Patches`, `Textures`, `Sounds`, `Assemblies`, `.git`, `.vs`, `bin`, `obj`, `__pycache__`, backup directories and service files such as `About.xml`, `LoadFolders.xml`, `Manifest.xml` and `PublishedFileId.xml`. Text in DLLs is not extracted.

Export is not restricted to `Defs` directories. However, outside English Keyed, the separate mod builder only handles XML with a `<Defs>` root and Defs with a direct `defName`. Other exported rows may remain unmatched in the report.

- **One target version per build:** version filtering uses path components such as `1.5` or `1.6`, not `LoadFolders.xml` rules. Common paths remain included.
- **Unnamed Defs:** templates without `defName` are skipped during package generation and reported.
- **Lists and repeated tags:** unusual loaders, repeated tags or duplicate keys may require manual review of `DefInjected`.
- **Nested XML:** for `<text>Before <b>war</b></text>`, extraction only reads the text before the first child for the `text` element.
- **CSV paths:** paths outside the selected mod root via `../` or absolute paths are rejected. This check does not resolve symbolic links or junctions; use trusted CSV files and directories.

**Do not delete the source mod's `Languages/` directory.** It may contain required name lists, grammar rules and string files, in addition to translations. Removing it can cause errors such as `No string files for Name/...` or `Grammar unresolvable`.

## Legacy Edit original mode

This mode asks for confirmation, backs up XML to `RimWorldTranslator_Backups/<timestamp>/` inside the source mod, and applies translations directly to source text nodes.

Steam Workshop updates can overwrite these edits. The mode has no target-version filter or placeholder-mismatch validation. Check the CSV manually; a separate translation mod is recommended for normal use.

## Review the CSV

Check numbers, booleans, enum-like words, PascalCase, paths and code-like values. Remove clearly technical rows. A word such as `North` or `Melee` can also be a real interface label; use its tag and source XML context to decide.

If text is missing, add the tag to Extra tags and export again with the correct saved CSV available for Smart Merge. Empty translations and `UNUSED` rows are skipped during build and import.

## Development

```text
rimworld_translator.py        — GUI, extraction and package builder
test_translator.py            — scanner, merge, placeholder and package tests
.github/workflows/release.yml — Windows build workflow
```

Run the existing tests:

```bash
python -m unittest -v
```

They cover placeholder round trips, parent-path rejection, Smart Merge restoration, nested Def keys, English Keyed scanning, source preservation, version filtering, broken placeholders and versioned overrides.

## License

MIT. See [LICENSE](LICENSE) for copyright information.

The expanded Russian guide is based on [AbsolutSSed's PR #1](https://github.com/laskinss27-cmyk/rimworld-mod-translator/pull/1), with corrections checked against the current implementation.
