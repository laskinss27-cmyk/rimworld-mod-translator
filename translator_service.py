"""UI-neutral workflows used by the Qt application."""

import csv
import os
import shutil
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime

from rimworld_translator import (
    build_translation_package,
    collect_identifiers,
    indent_element,
    is_definitely_technical,
    is_english_keyed_path,
    is_translatable,
    load_existing_translations,
    mask_placeholders,
    read_mod_metadata,
    safe_join,
    sanitize_component,
    split_relative_path,
    unmask_placeholders,
)


def _noop(*_args, **_kwargs):
    pass


def find_xml_files(directory):
    """Find source Def XML and English Keyed files that can be translated."""
    xml_files = []
    skip_dirs = {
        ".git", ".vs", "bin", "obj", "__pycache__", "patches",
        "textures", "sounds", "assemblies", "rimworldtranslator_backups",
    }
    skip_files = {"loadfolders.xml", "about.xml", "manifest.xml", "publishedfileid.xml"}

    for root_dir, dirs, files in os.walk(directory):
        rel_parts = [
            part.lower()
            for part in split_relative_path(os.path.relpath(root_dir, directory))
        ]
        dirs[:] = [directory_name for directory_name in dirs if directory_name.lower() not in skip_dirs]
        in_languages = "languages" in rel_parts
        in_english_keyed = any(
            rel_parts[index:index + 3] == ["languages", "english", "keyed"]
            for index in range(max(0, len(rel_parts) - 2))
        )
        if any(part in skip_dirs for part in rel_parts):
            continue
        if in_languages and not in_english_keyed:
            continue
        for filename in files:
            if filename.lower().endswith(".xml") and filename.lower() not in skip_files:
                xml_files.append(os.path.join(root_dir, filename))
    return sorted(xml_files, key=str.lower)


def inspect_mod(mod_root):
    metadata = read_mod_metadata(mod_root)
    metadata["xml_count"] = len(find_xml_files(mod_root))
    return metadata


def _extract_rows(xml_file, relative_path, known_ids, force_tags, old_translations):
    tree = ET.parse(xml_file)
    root = tree.getroot()
    rows = []
    seen = set()
    new_count = merged_count = 0

    for element in root.iter():
        if not isinstance(element.tag, str) or not element.text or not element.text.strip():
            continue

        tag_name = element.tag
        source_text = element.text.strip()
        forced = tag_name.lower() in force_tags
        keyed_text = is_english_keyed_path(relative_path) and element is not root
        if not keyed_text:
            if forced and not is_definitely_technical(source_text):
                pass
            elif not is_translatable(tag_name, source_text, known_ids):
                continue

        key = (relative_path, source_text)
        seen.add(key)
        masked_source, placeholder_map = mask_placeholders(source_text)
        previous_translation = old_translations.get(key, "")
        if previous_translation:
            masked_translation, _ = mask_placeholders(previous_translation)
            status = "DONE"
            merged_count += 1
        else:
            masked_translation = ""
            status = "NEW"
            new_count += 1
        rows.append([
            relative_path,
            tag_name,
            "//" + tag_name,
            masked_source,
            masked_translation,
            status,
            placeholder_map,
        ])
    return rows, seen, new_count, merged_count


def export_translations(mod_root, output_file, force_tags=None, progress=None, log=None):
    """Export translatable text to a merge-friendly CSV file."""
    progress = progress or _noop
    log = log or _noop
    force_tags = {
        item.strip().lower() for item in (force_tags or "").split(",") if item.strip()
    }
    xml_files = find_xml_files(mod_root)
    if not xml_files:
        raise ValueError("No translatable XML files were found in the selected mod.")

    log("Found XML files: " + str(len(xml_files)), "INFO")
    progress(5)
    known_ids = collect_identifiers(xml_files)
    log("Known technical identifiers: " + str(len(known_ids)), "INFO")
    progress(15)

    old_translations = load_existing_translations(output_file)
    if old_translations:
        log("Previous translations preserved: " + str(len(old_translations)), "SUCCESS")

    all_rows = []
    seen_keys = set()
    new_count = merged_count = files_with_text = 0
    errors = []
    for index, xml_file in enumerate(xml_files):
        relative_path = os.path.relpath(xml_file, mod_root)
        try:
            rows, seen, new_rows, merged_rows = _extract_rows(
                xml_file, relative_path, known_ids, force_tags, old_translations,
            )
            all_rows.extend(rows)
            seen_keys.update(seen)
            new_count += new_rows
            merged_count += merged_rows
            if rows:
                files_with_text += 1
                log(relative_path + ": " + str(len(rows)) + " rows", "INFO")
        except (ET.ParseError, OSError) as exc:
            message = relative_path + ": " + str(exc)
            errors.append(message)
            log(message, "ERROR")
        progress(15 + int((index + 1) / len(xml_files) * 75))

    unused_count = 0
    for (file_path, original), translation in old_translations.items():
        if (file_path, original) not in seen_keys:
            all_rows.append([file_path, "", "", original, translation, "UNUSED", ""])
            unused_count += 1

    output_directory = os.path.dirname(os.path.abspath(output_file))
    os.makedirs(output_directory, exist_ok=True)
    temporary = output_file + ".tmp"
    with open(temporary, "w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow([
            "File", "Tag", "XPath", "Original Text",
            "Translation", "Status", "Placeholders",
        ])
        writer.writerows(all_rows)
    os.replace(temporary, output_file)
    progress(100)

    return {
        "output": output_file,
        "rows": len(all_rows) - unused_count,
        "new": new_count,
        "merged": merged_count,
        "unused": unused_count,
        "files": files_with_text,
        "scanned_files": len(xml_files),
        "errors": errors,
    }


def _apply_translations_to_file(xml_file, items):
    tree = ET.parse(xml_file)
    root = tree.getroot()
    pending = defaultdict(list)
    for tag, original, translation in items:
        pending[(tag, original)].append(translation)

    applied = 0
    for element in root.iter():
        if not isinstance(element.tag, str) or not element.text or not element.text.strip():
            continue
        key = (element.tag, element.text.strip())
        if pending[key]:
            element.text = pending[key].pop(0)
            applied += 1

    skipped = sum(len(values) for values in pending.values())
    if applied:
        indent_element(root)
        temporary = xml_file + ".tmp"
        with open(temporary, "w", encoding="utf-8", newline="\n") as output:
            output.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            tree.write(output, encoding="unicode", short_empty_elements=False)
            output.write("\n")
        os.replace(temporary, xml_file)
    return applied, skipped


def import_into_original(mod_root, csv_file, progress=None, log=None):
    """Legacy import with path validation and recoverable XML backups."""
    progress = progress or _noop
    log = log or _noop
    by_file = defaultdict(list)
    skipped_unused = 0
    with open(csv_file, "r", encoding="utf-8-sig") as input_file:
        for row in csv.DictReader(input_file):
            if (row.get("Status") or "").strip().upper() == "UNUSED":
                skipped_unused += 1
                continue
            file_path = (row.get("File") or "").strip()
            tag = (row.get("Tag") or "").strip()
            translation = row.get("Translation") or ""
            if not file_path or not tag or not translation.strip():
                continue
            placeholder_map = row.get("Placeholders") or ""
            by_file[file_path].append((
                tag,
                unmask_placeholders(row.get("Original Text") or "", placeholder_map),
                unmask_placeholders(translation, placeholder_map),
            ))
    if not by_file:
        raise ValueError("The CSV does not contain any completed translations.")

    backup_root = os.path.join(
        mod_root,
        "RimWorldTranslator_Backups",
        datetime.now().strftime("%Y%m%d_%H%M%S"),
    )
    updated_files = applied_units = skipped_units = 0
    items_list = list(by_file.items())
    for index, (relative_path, items) in enumerate(items_list):
        try:
            source_path = safe_join(mod_root, relative_path)
            if not os.path.exists(source_path):
                log("File not found: " + relative_path, "WARNING")
                skipped_units += len(items)
                continue
            backup_path = safe_join(backup_root, relative_path)
            os.makedirs(os.path.dirname(backup_path), exist_ok=True)
            shutil.copy2(source_path, backup_path)
            applied, skipped = _apply_translations_to_file(source_path, items)
            applied_units += applied
            skipped_units += skipped
            if applied:
                updated_files += 1
                log(relative_path + ": " + str(applied) + " applied", "SUCCESS")
        except (ValueError, OSError, ET.ParseError) as exc:
            log(relative_path + ": " + str(exc), "ERROR")
            skipped_units += len(items)
        progress(int((index + 1) / len(items_list) * 100))

    return {
        "files": updated_files,
        "applied": applied_units,
        "skipped": skipped_units,
        "unused": skipped_unused,
        "backup": backup_root if os.path.exists(backup_root) else "",
    }


def default_translation_output(mod_root, language_folder):
    metadata = read_mod_metadata(mod_root)
    folder_name = (
        sanitize_component(metadata["name"])
        + "_" + sanitize_component(language_folder, "Russian")
        + "_Translation"
    )
    return folder_name


__all__ = [
    "build_translation_package",
    "default_translation_output",
    "export_translations",
    "find_xml_files",
    "import_into_original",
    "inspect_mod",
    "read_mod_metadata",
]
