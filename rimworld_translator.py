import os
import subprocess
import platform
import shutil
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from datetime import datetime
import re
import json
import csv
from collections import defaultdict, Counter

# ── DPI awareness (Windows) ───────────────────────────────────────────────────
try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

PLACEHOLDER_RE = re.compile(r"\{[^{}\r\n]+\}|\[[A-Za-z_]\w*\]")


# ── Placeholder helpers ───────────────────────────────────────────────────────

def mask_placeholders(text):
    holders = PLACEHOLDER_RE.findall(text)
    if not holders:
        return text, ""
    mapping = {}
    for i, h in enumerate(holders):
        if h not in mapping:
            mapping[h] = f"__RWPH_{i}__"
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
    "storefactionleaderas",
    # Name tag — almost always technical (render layers, quest vars, etc.)
    "name",
    # Script / quest logic tags
    "outcome", "storeas", "delayticks", "insigtop",
    "factionrelationkind", "mindanger", "allowedthreats",
    "tale", "method",
    # PawnKind / quality / skill enum tags
    "itemquality", "quality", "skill", "minexpectation",
    "rotstage", "tradecurrency", "containerreservationlayer",
    # Render / rotation / flag tags
    "offsetmode", "fliponrotation", "hairgender",
    "relativerotation", "skipflag",
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
    "text", "title", "message", "customlabel",
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
    # Backstory / faction visible text
    "titleshort", "leadertitle", "pawnsingular", "pawnsplural",
    "chargenoun", "gizmolable", "verbgizmodesc",
    "optiontext", "activatelabelstring", "countdownlabel",
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
    # Direction / side enums (SpectateRectSide etc.)
    "up", "down", "left", "right", "vertical", "horizontal", "all",
    "north", "south", "east", "west",
    "clockwise", "counterclockwise",
    # Quality / expectation enums
    "awful", "poor", "good", "excellent", "masterwork", "legendary",
    "moderate", "noble", "royal",
    # Faction / threat enums
    "hostile", "neutral", "ally",
    "raids", "high", "low", "critical",
    "free", "standing", "fresh", "rotten",
    "any", "favor",
    # Misc enums
    "finish", "reverse", "empty", "full",
    "shooting", "construction", "mining", "cooking",
    "growing", "crafting", "hunting", "research",
    "medicine", "artistic", "plants", "animals",
    "intellectual", "social",
    "beard", "raid",
    "ultratech", "midworld", "glitterworld",
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
        # For known text tags, only skip hard-technical values
        # (numbers, booleans, paths, UUIDs etc.) but NOT enum words
        # because "Finish", "Reverse" etc. are valid button labels
        if not t:
            return False
        if re.match(r"^-?\d+([.,]\d+)?f?$", t):
            return False
        if t.lower() in ("true", "false", "null", "none"):
            return False
        if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}", t, re.I):
            return False
        if re.match(r"^(\w+[/\\])+\w+(\.\w+)?$", t):
            return False
        if t.startswith("<") or t.startswith("$"):
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
                placeholder_map = row.get("Placeholders") or ""
                original = unmask_placeholders(original, placeholder_map)
                translation = unmask_placeholders(translation, placeholder_map)
                if file_path and original and translation.strip():
                    translations[(file_path, original)] = translation
    except Exception:
        pass
    return translations


def safe_join(root_dir, relative_path):
    """Join an untrusted CSV path without allowing it to escape the mod root."""
    root_abs = os.path.abspath(root_dir)
    candidate = os.path.abspath(os.path.join(root_abs, relative_path))
    try:
        common = os.path.commonpath([root_abs, candidate])
    except ValueError:
        raise ValueError("Path is outside the selected mod folder: " + relative_path)
    if os.path.normcase(common) != os.path.normcase(root_abs):
        raise ValueError("Path is outside the selected mod folder: " + relative_path)
    return candidate


def split_relative_path(path):
    return [part for part in re.split(r"[\\/]+", path) if part and part != "."]


def path_game_version(path):
    for part in split_relative_path(path):
        if re.match(r"^\d+\.\d+$", part):
            return part
    return None


def parse_compatible_versions(value):
    """Parse a user-declared comma-separated list, preserving version order."""
    versions = []
    for item in value.split(","):
        version = item.strip()
        if not re.fullmatch(r"\d+\.\d+", version):
            raise ValueError("Expected versions separated by commas, for example: 1.4, 1.5")
        if version not in versions:
            versions.append(version)
    return versions


def sanitize_component(value, fallback="Translation"):
    cleaned = re.sub(r"[^\w.()\- ]+", "_", (value or "").strip(), flags=re.UNICODE)
    cleaned = cleaned.strip(" ._")
    return cleaned or fallback


def package_suffix(value):
    cleaned = re.sub(r"[^a-z0-9]+", "", (value or "").lower())
    return cleaned or "translation"


def extract_placeholders(text):
    return Counter(PLACEHOLDER_RE.findall(text or ""))


def load_translation_rows(csv_path):
    """Load translated CSV rows while preserving compatibility with older exports."""
    rows = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("Status") or "").strip().upper() == "UNUSED":
                continue
            file_path = (row.get("File") or "").strip()
            tag = (row.get("Tag") or "").strip()
            original = row.get("Original Text") or ""
            translation = row.get("Translation") or ""
            placeholder_map = row.get("Placeholders") or ""
            if not file_path or not tag or not translation.strip():
                continue
            original = unmask_placeholders(original, placeholder_map)
            translation = unmask_placeholders(translation, placeholder_map)
            rows.append({
                "file": file_path,
                "tag": tag,
                "original": original,
                "translation": translation,
            })
    return rows


def read_mod_metadata(mod_root):
    metadata = {
        "name": os.path.basename(os.path.abspath(mod_root)),
        "package_id": "",
        "versions": [],
    }
    about_path = os.path.join(mod_root, "About", "About.xml")
    if not os.path.exists(about_path):
        return metadata
    try:
        root = ET.parse(about_path).getroot()
        name = root.findtext("name")
        package_id = root.findtext("packageId")
        if name and name.strip():
            metadata["name"] = name.strip()
        if package_id and package_id.strip():
            metadata["package_id"] = package_id.strip()
        versions = root.find("supportedVersions")
        if versions is not None:
            metadata["versions"] = [
                item.text.strip() for item in versions
                if item.text and item.text.strip()
            ]
    except (ET.ParseError, OSError):
        pass
    return metadata


def _direct_child_text(element, tag_name):
    for child in element:
        if isinstance(child.tag, str) and child.tag == tag_name:
            return (child.text or "").strip()
    return ""


def iter_def_translation_targets(xml_file):
    """Return concrete Def text nodes and their best-effort DefInjected keys."""
    tree = ET.parse(xml_file)
    root = tree.getroot()
    if not isinstance(root.tag, str) or root.tag.lower() != "defs":
        return [], ["Root element is not <Defs>"]

    targets = []
    warnings = []

    def walk(parent, def_type, def_name, path):
        li_index = 0
        tag_counts = Counter(
            child.tag for child in parent
            if isinstance(child.tag, str) and child.tag != "li"
        )
        seen_tags = Counter()
        for child in parent:
            if not isinstance(child.tag, str):
                continue
            tag = child.tag
            if tag == "defName" and not path:
                continue
            if tag == "li":
                segment = str(li_index)
                li_index += 1
            else:
                segment = tag
                if tag_counts[tag] > 1:
                    warnings.append(
                        "Repeated non-list tag may need manual review: "
                        + def_name + "." + ".".join(path + [tag])
                    )
                seen_tags[tag] += 1
            new_path = path + [segment]
            text = (child.text or "").strip()
            if text:
                targets.append({
                    "tag": tag,
                    "original": text,
                    "def_type": def_type,
                    "def_name": def_name,
                    "key": def_name + "." + ".".join(new_path),
                    "uses_list_index": tag == "li" or any(p.isdigit() for p in new_path),
                })
            if len(child):
                walk(child, def_type, def_name, new_path)

    for def_element in root:
        if not isinstance(def_element.tag, str):
            continue
        def_name = _direct_child_text(def_element, "defName")
        if not def_name:
            abstract_name = (def_element.get("Name") or "").strip()
            label = abstract_name or def_element.tag
            warnings.append("Skipped abstract or unnamed Def: " + label)
            continue
        walk(def_element, def_element.tag, def_name, [])

    return targets, warnings


def is_english_keyed_path(relative_path):
    parts = [part.lower() for part in split_relative_path(relative_path)]
    for index in range(len(parts) - 2):
        if parts[index:index + 3] == ["languages", "english", "keyed"]:
            return True
    return False


def keyed_output_relative_path(relative_path):
    parts = split_relative_path(relative_path)
    lowered = [part.lower() for part in parts]
    for index in range(len(parts) - 2):
        if lowered[index:index + 3] == ["languages", "english", "keyed"]:
            tail = parts[index + 3:]
            return os.path.join(*tail) if tail else "Keyed.xml"
    return os.path.basename(relative_path)


def defs_output_relative_path(relative_path, def_type):
    parts = split_relative_path(relative_path)
    lowered = [part.lower() for part in parts]
    try:
        defs_index = lowered.index("defs")
        tail = parts[defs_index + 1:]
    except ValueError:
        tail = [os.path.basename(relative_path)]
    if not tail:
        tail = ["Generated.xml"]
    return os.path.join("DefInjected", sanitize_component(def_type), *tail)


def indent_element(element, level=0):
    indentation = "\n" + "  " * level
    if len(element):
        if not element.text or not element.text.strip():
            element.text = indentation + "  "
        for child in element:
            indent_element(child, level + 1)
        if not element[-1].tail or not element[-1].tail.strip():
            element[-1].tail = indentation
    if level and (not element.tail or not element.tail.strip()):
        element.tail = indentation


def atomic_write_xml(path, root):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    indent_element(root)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8", newline="\n") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        ET.ElementTree(root).write(f, encoding="unicode", short_empty_elements=False)
        f.write("\n")
    os.replace(temporary, path)


def build_translation_package(mod_root, csv_path, output_root, language_folder,
                              game_version, compatible_versions=None):
    """Build from game_version files; compatibility is a separate declaration.

    compatible_versions is a comma-separated string. If omitted, preserve the
    single-version behavior of existing callers. Declared compatibility does
    not change source selection or establish compatibility with the game.
    """
    if game_version and not re.fullmatch(r"\d+\.\d+", game_version):
        raise ValueError("Expected one source version, for example: 1.6")
    metadata = read_mod_metadata(mod_root)
    if compatible_versions is None:
        declared_versions = [game_version or (
            metadata["versions"][-1] if metadata["versions"] else "1.6"
        )]
    else:
        declared_versions = parse_compatible_versions(compatible_versions)

    rows = load_translation_rows(csv_path)
    rows_by_file = defaultdict(list)
    for row in rows:
        version = path_game_version(row["file"])
        if version and game_version and version != game_version:
            continue
        rows_by_file[row["file"]].append(row)

    warnings = []
    invalid_placeholders = 0
    unmatched = 0
    generated_entries = 0
    groups = defaultdict(dict)

    ordered_files = sorted(
        rows_by_file.items(),
        key=lambda item: (
            1 if path_game_version(item[0]) else 0,
            item[0].lower(),
        ),
    )
    for relative_path, file_rows in ordered_files:
        try:
            source_path = safe_join(mod_root, relative_path)
        except ValueError as exc:
            warnings.append(str(exc))
            unmatched += len(file_rows)
            continue
        if not os.path.exists(source_path):
            warnings.append("Source file not found: " + relative_path)
            unmatched += len(file_rows)
            continue

        pending = defaultdict(list)
        for row in file_rows:
            pending[(row["tag"], row["original"])].append(row)

        if is_english_keyed_path(relative_path):
            try:
                root = ET.parse(source_path).getroot()
            except (ET.ParseError, OSError) as exc:
                warnings.append("Could not parse Keyed file " + relative_path + ": " + str(exc))
                unmatched += len(file_rows)
                continue
            output_rel = os.path.join("Keyed", keyed_output_relative_path(relative_path))
            group_key = ("keyed", output_rel)
            for element in root:
                if not isinstance(element.tag, str) or not element.text:
                    continue
                key = (element.tag, element.text.strip())
                if not pending[key]:
                    continue
                row = pending[key].pop(0)
                if extract_placeholders(row["original"]) != extract_placeholders(row["translation"]):
                    warnings.append("Placeholder mismatch: " + relative_path + " :: " + element.tag)
                    invalid_placeholders += 1
                    continue
                groups[group_key][element.tag] = (row["original"], row["translation"])
                generated_entries += 1
        else:
            try:
                targets, target_warnings = iter_def_translation_targets(source_path)
            except (ET.ParseError, OSError) as exc:
                warnings.append("Could not parse Def file " + relative_path + ": " + str(exc))
                unmatched += len(file_rows)
                continue
            warnings.extend(relative_path + ": " + item for item in target_warnings)
            for target in targets:
                key = (target["tag"], target["original"])
                if not pending[key]:
                    continue
                row = pending[key].pop(0)
                if extract_placeholders(row["original"]) != extract_placeholders(row["translation"]):
                    warnings.append("Placeholder mismatch: " + relative_path + " :: " + target["key"])
                    invalid_placeholders += 1
                    continue
                output_rel = defs_output_relative_path(relative_path, target["def_type"])
                group_key = ("def", output_rel)
                if target["key"] in groups[group_key]:
                    warnings.append("Duplicate DefInjected key, last value used: " + target["key"])
                groups[group_key][target["key"]] = (row["original"], row["translation"])
                generated_entries += 1

        unmatched += sum(len(items) for items in pending.values())

    generated_entries = sum(len(entries) for entries in groups.values())
    language_root = os.path.join(output_root, "Languages", language_folder)
    for (_, relative_output), entries in groups.items():
        output_path = os.path.join(language_root, relative_output)
        language_data = ET.Element("LanguageData")
        for key, (original, translation) in sorted(entries.items()):
            language_data.append(ET.Comment(" EN: " + original.replace("--", "—") + " "))
            node = ET.SubElement(language_data, key)
            node.text = translation
        atomic_write_xml(output_path, language_data)

    about = ET.Element("ModMetaData")
    name = metadata["name"] + " — " + language_folder + " translation"
    ET.SubElement(about, "name").text = name
    ET.SubElement(about, "author").text = "Generated with RimWorld Mod Translator"
    original_package = metadata["package_id"]
    if original_package:
        translated_package = original_package + ".translation." + package_suffix(language_folder)
    else:
        translated_package = "local." + package_suffix(metadata["name"]) + ".translation." + package_suffix(language_folder)
        warnings.append("Original About.xml has no packageId; dependency must be checked manually.")
    ET.SubElement(about, "packageId").text = translated_package
    supported = ET.SubElement(about, "supportedVersions")
    for version in declared_versions:
        ET.SubElement(supported, "li").text = version
    if original_package:
        dependencies = ET.SubElement(about, "modDependencies")
        dependency = ET.SubElement(dependencies, "li")
        ET.SubElement(dependency, "packageId").text = original_package
        ET.SubElement(dependency, "displayName").text = metadata["name"]
        load_after = ET.SubElement(about, "loadAfter")
        ET.SubElement(load_after, "li").text = original_package
    ET.SubElement(about, "description").text = (
        language_folder + " translation for " + metadata["name"]
        + ". Generated as a separate mod; the original mod is not modified."
    )
    atomic_write_xml(os.path.join(output_root, "About", "About.xml"), about)

    report_path = os.path.join(output_root, "Generation report.txt")
    os.makedirs(output_root, exist_ok=True)
    with open(report_path, "w", encoding="utf-8", newline="\n") as report:
        report.write("RimWorld Mod Translator — safe translation package\n")
        report.write("Source mod: " + metadata["name"] + "\n")
        report.write("Target language folder: " + language_folder + "\n")
        report.write("Source RimWorld version: " + (game_version or "auto") + "\n")
        report.write("Declared compatible versions: " + ", ".join(declared_versions) + "\n")
        report.write("Listed compatibility is not verified by the translator.\n")
        report.write("Generated entries: " + str(generated_entries) + "\n")
        report.write("Unmatched CSV rows: " + str(unmatched) + "\n")
        report.write("Placeholder mismatches skipped: " + str(invalid_placeholders) + "\n")
        if warnings:
            report.write("\nWarnings:\n")
            for warning in warnings:
                report.write("- " + warning + "\n")

    return {
        "entries": generated_entries,
        "files": len(groups),
        "unmatched": unmatched,
        "placeholder_mismatches": invalid_placeholders,
        "warnings": warnings,
        "output": output_root,
    }


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
        "build_mod":         "Создать мод-перевод",
        "import_":           "Изменить оригинал",
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
        "target_language":   "Имя папки языка RimWorld (например, Russian)",
        "source_version":    "Версия исходников (например, 1.6).\nБудут взяты файлы этой версии и общие файлы мода.",
        "compatible_versions": "Совместимые версии через запятую (например, 1.4, 1.5).\nСписок будет записан в About.xml и не меняет выбор исходников.\nСовместимость указываете вы, программа её не проверяет.",
        "invalid_compatible_versions": "Укажите одну или несколько версий через запятую, например: 1.4, 1.5",
        "choose_output":     "Куда сохранить отдельный мод-перевод",
        "build_started":     "Создание отдельного мода-перевода…",
        "build_done":        "Мод-перевод создан!\nПапка: {output}\nФайлов: {files}\nСтрок: {entries}\nНе сопоставлено: {unmatched}",
        "build_err_status":  "Ошибка создания мода-перевода",
        "backup_created":    "Резервная копия оригинальных XML: {0}",
        "legacy_warning":    "Этот режим изменит XML оригинального мода. Перед изменением будет создана резервная копия. Продолжить?",
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
        "build_mod":         "Build translation mod",
        "import_":           "Edit original",
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
        "target_language":   "RimWorld language folder name (for example, Russian)",
        "source_version":    "Source version (for example, 1.6).\nFiles for this version and common mod files will be used.",
        "compatible_versions": "Compatible versions, separated by commas (for example, 1.4, 1.5).\nThis list goes into About.xml and does not change source selection.\nYou declare compatibility; the application does not verify it.",
        "invalid_compatible_versions": "Enter one or more versions separated by commas, for example: 1.4, 1.5",
        "choose_output":     "Choose where to save the separate translation mod",
        "build_started":     "Building separate translation mod…",
        "build_done":        "Translation mod created!\nFolder: {output}\nFiles: {files}\nEntries: {entries}\nUnmatched: {unmatched}",
        "build_err_status":  "Translation mod build error",
        "backup_created":    "Original XML backup: {0}",
        "legacy_warning":    "This mode edits the original mod XML. A backup will be created first. Continue?",
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

        self._btn_build = ttk.Button(
            actions, text=s["build_mod"],
            style="Accent.TButton", command=self.build_translation_mod,
        )
        self._btn_build.pack(side=tk.LEFT, padx=(0, 8))

        self._btn_import = ttk.Button(
            actions, text=s["import_"], command=self.import_translation,
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
        self._btn_build.config(text=s["build_mod"])
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
        skip = {".git", ".vs", "bin", "obj", "__pycache__", "patches",
                "textures", "sounds", "assemblies", "rimworldtranslator_backups"}
        skip_files = {"loadfolders.xml", "about.xml", "manifest.xml", "publishedfileid.xml"}
        try:
            for root_dir, dirs, files in os.walk(directory):
                rel_parts = [part.lower() for part in split_relative_path(
                    os.path.relpath(root_dir, directory)
                )]
                in_languages = "languages" in rel_parts
                in_english_keyed = any(
                    rel_parts[index:index + 3] == ["languages", "english", "keyed"]
                    for index in range(max(0, len(rel_parts) - 2))
                )
                if any(part in skip for part in rel_parts):
                    continue
                if in_languages and not in_english_keyed:
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
            keyed_text = is_english_keyed_path(relative_path) and elem is not root

            if keyed_text:
                pass
            elif forced and not is_definitely_technical(text):
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

    # ── Safe translation mod build ──────────────────────────────────────────

    def build_translation_mod(self):
        if not self.source_dir.get() or not os.path.exists(self.source_dir.get()):
            messagebox.showerror("", self.t("need_folder"))
            return

        csv_file = filedialog.askopenfilename(
            title=self.t("choose_csv"),
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not csv_file:
            return

        metadata = read_mod_metadata(self.source_dir.get())
        default_version = metadata["versions"][-1] if metadata["versions"] else "1.6"
        language_folder = simpledialog.askstring(
            self.t("build_mod"), self.t("target_language"),
            initialvalue="Russian", parent=self.root,
        )
        if not language_folder:
            return
        language_folder = sanitize_component(language_folder, "Russian")

        source_version = simpledialog.askstring(
            self.t("build_mod"), self.t("source_version"),
            initialvalue=default_version, parent=self.root,
        )
        if source_version is None:
            return
        source_version = source_version.strip()
        if not re.fullmatch(r"\d+\.\d+", source_version):
            messagebox.showerror("", self.t("source_version"))
            return

        compatible_versions = simpledialog.askstring(
            self.t("build_mod"), self.t("compatible_versions"),
            initialvalue=source_version, parent=self.root,
        )
        if compatible_versions is None:
            return
        try:
            parse_compatible_versions(compatible_versions)
        except ValueError:
            messagebox.showerror("", self.t("invalid_compatible_versions"))
            return

        output_parent = filedialog.askdirectory(title=self.t("choose_output"))
        if not output_parent:
            return
        folder_name = (
            sanitize_component(metadata["name"]) + "_"
            + sanitize_component(language_folder) + "_Translation"
        )
        output_root = os.path.join(output_parent, folder_name)
        if os.path.exists(output_root):
            output_root += "_" + datetime.now().strftime("%Y%m%d_%H%M%S")

        self.clear_log()
        self.status_var.set(self.t("build_started"))
        self.log(self.t("build_started"))
        self.update_progress(20)
        try:
            result = build_translation_package(
                self.source_dir.get(), csv_file, output_root,
                language_folder, source_version,
                compatible_versions=compatible_versions,
            )
            self.update_progress(100)
            self.log(self.t("saved_to", output_root), "SUCCESS")
            self.log(self.t("total_rows", result["entries"]), "SUCCESS")
            if result["unmatched"]:
                self.log(self.t("not_applied", result["unmatched"]), "WARNING")
            for warning in result["warnings"][:50]:
                self.log(warning, "WARNING")
            if len(result["warnings"]) > 50:
                self.log("Additional warnings are in Generation report.txt", "WARNING")
            self.status_var.set(self.t("done_imp", result["files"], result["entries"]))
            messagebox.showinfo(
                self.t("done_title"),
                self.t("build_done", **result),
            )
        except Exception as exc:
            self.log(self.t("critical", exc), "ERROR")
            self.status_var.set(self.t("build_err_status"))
            messagebox.showerror("", str(exc))
        finally:
            self.update_progress(0)

    # ── Import ────────────────────────────────────────────────────────────────

    def import_translation(self):
        if not self.source_dir.get() or not os.path.exists(self.source_dir.get()):
            messagebox.showerror("", self.t("need_folder"))
            return
        if not messagebox.askyesno(self.t("import_"), self.t("legacy_warning")):
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
            backup_root = os.path.join(
                self.source_dir.get(), "RimWorldTranslator_Backups",
                datetime.now().strftime("%Y%m%d_%H%M%S"),
            )

            for i, (fp, items) in enumerate(items_list):
                try:
                    full_path = safe_join(self.source_dir.get(), fp)
                except ValueError as exc:
                    self.log(str(exc), "ERROR")
                    skipped_units += len(items)
                    continue
                if not os.path.exists(full_path):
                    self.log(self.t("file_not_found", fp), "WARNING")
                    skipped_units += len(items)
                    continue
                try:
                    backup_path = safe_join(backup_root, fp)
                    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                    shutil.copy2(full_path, backup_path)
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

            if os.path.exists(backup_root):
                self.log(self.t("backup_created", backup_root), "SUCCESS")

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
