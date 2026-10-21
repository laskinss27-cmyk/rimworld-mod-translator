import csv
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import Mock, patch

from rimworld_translator import (
    build_translation_package,
    iter_def_translation_targets,
    load_existing_translations,
    mask_placeholders,
    parse_compatible_versions,
    RimWorldTranslator,
    safe_join,
    unmask_placeholders,
)


class TranslatorHelpersTests(unittest.TestCase):
    def test_parses_compatible_versions_and_removes_duplicates_in_order(self):
        self.assertEqual(
            parse_compatible_versions(" 1.3, 1.2 , 1.3, 1.6 "),
            ["1.3", "1.2", "1.6"],
        )
        self.assertEqual(parse_compatible_versions("1.2"), ["1.2"])

    def test_rejects_empty_or_malformed_compatible_versions(self):
        for value in ("", " ", ",", "1.2,", ",1.2", "1.2,,1.3",
                      "1.2 1.3", "v1.2", "1.2.0", "1.2\n1.3"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_compatible_versions(value)

    def test_placeholder_round_trip_includes_numeric_and_grammar(self):
        source = "Use {0} on {PAWN_nameDef}; {PAWN_gender ? his : her} [PAWN_pronoun]"
        masked, mapping = mask_placeholders(source)
        self.assertNotIn("{0}", masked)
        self.assertNotIn("{PAWN_nameDef}", masked)
        self.assertEqual(unmask_placeholders(masked, mapping), source)

    def test_safe_join_rejects_parent_escape(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                safe_join(root, os.path.join("..", "outside.xml"))

    def test_smart_merge_unmasks_placeholder_tokens(self):
        with tempfile.TemporaryDirectory() as temp:
            csv_path = os.path.join(temp, "translations.csv")
            with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "File", "Tag", "XPath", "Original Text",
                    "Translation", "Status", "Placeholders",
                ])
                writer.writerow([
                    "Defs/Test.xml", "label", "//label",
                    "Use __RWPH_0__", "Использовать __RWPH_0__", "DONE",
                    "__RWPH_0__={0}",
                ])
            translations = load_existing_translations(csv_path)
            self.assertEqual(
                translations[("Defs/Test.xml", "Use {0}")],
                "Использовать {0}",
            )

    def test_def_keys_include_nested_fields_and_list_indexes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, "Things.xml")
            with open(path, "w", encoding="utf-8") as f:
                f.write(
                    "<Defs><ThingDef><defName>TestGun</defName>"
                    "<label>test gun</label><ingestible>"
                    "<ingestCommandString>Use {0}</ingestCommandString>"
                    "</ingestible><verbs><li><label>first mode</label></li>"
                    "<li><label>second mode</label></li></verbs>"
                    "</ThingDef></Defs>"
                )
            targets, warnings = iter_def_translation_targets(path)
            keys = {target["key"] for target in targets}
            self.assertIn("TestGun.label", keys)
            self.assertIn("TestGun.ingestible.ingestCommandString", keys)
            self.assertIn("TestGun.verbs.0.label", keys)
            self.assertIn("TestGun.verbs.1.label", keys)
            self.assertEqual(warnings, [])


class TranslationPackageTests(unittest.TestCase):
    def _write(self, root, relative, content):
        path = os.path.join(root, *relative.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def _write_csv(self, path, rows):
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "File", "Tag", "XPath", "Original Text",
                "Translation", "Status", "Placeholders",
            ])
            writer.writerows(rows)

    def test_scanner_includes_english_keyed_but_not_other_languages(self):
        with tempfile.TemporaryDirectory() as source:
            defs_path = self._write(source, "Defs/Test.xml", "<Defs></Defs>")
            keyed_path = self._write(
                source, "Languages/English/Keyed/UI.xml",
                "<LanguageData><Key>Text</Key></LanguageData>",
            )
            self._write(
                source, "Languages/Russian/Keyed/UI.xml",
                "<LanguageData><Key>Текст</Key></LanguageData>",
            )
            self._write(source, "Patches/Patch.xml", "<Patch></Patch>")
            app = RimWorldTranslator.__new__(RimWorldTranslator)
            found = {os.path.normcase(path) for path in app.find_xml_files(source)}
            self.assertIn(os.path.normcase(defs_path), found)
            self.assertIn(os.path.normcase(keyed_path), found)
            self.assertEqual(len(found), 2)

    def test_builds_separate_mod_and_leaves_source_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            source = os.path.join(temp, "SourceMod")
            output = os.path.join(temp, "OutputTranslation")
            os.makedirs(source)
            self._write(
                source, "About/About.xml",
                "<ModMetaData><name>Example Mod</name>"
                "<packageId>author.example</packageId>"
                "<supportedVersions><li>1.6</li></supportedVersions>"
                "</ModMetaData>",
            )
            defs_content = (
                "<Defs><ThingDef><defName>ExampleThing</defName>"
                "<label>example thing</label>"
                "<description>Uses {0} safely.</description>"
                "</ThingDef></Defs>"
            )
            defs_path = self._write(source, "1.6/Defs/Things.xml", defs_content)
            self._write(
                source, "Languages/English/Keyed/UI.xml",
                "<LanguageData><Example_Button>Open {0}</Example_Button></LanguageData>",
            )
            csv_path = os.path.join(temp, "translations.csv")
            self._write_csv(csv_path, [
                ["1.6/Defs/Things.xml", "label", "//label", "example thing", "пример", "NEW", ""],
                ["1.6/Defs/Things.xml", "description", "//description", "Uses {0} safely.", "Безопасно использует {0}.", "NEW", ""],
                ["Languages/English/Keyed/UI.xml", "Example_Button", "//Example_Button", "Open {0}", "Открыть {0}", "NEW", ""],
            ])

            result = build_translation_package(
                source, csv_path, output, "Russian", "1.6"
            )

            self.assertEqual(result["entries"], 3)
            self.assertEqual(result["unmatched"], 0)
            with open(defs_path, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), defs_content)

            def_output = os.path.join(
                output, "Languages", "Russian", "DefInjected",
                "ThingDef", "Things.xml",
            )
            def_root = ET.parse(def_output).getroot()
            self.assertEqual(def_root.findtext("ExampleThing.label"), "пример")
            self.assertEqual(
                def_root.findtext("ExampleThing.description"),
                "Безопасно использует {0}.",
            )

            keyed_output = os.path.join(
                output, "Languages", "Russian", "Keyed", "UI.xml"
            )
            keyed_root = ET.parse(keyed_output).getroot()
            self.assertEqual(keyed_root.findtext("Example_Button"), "Открыть {0}")

            about_root = ET.parse(os.path.join(output, "About", "About.xml")).getroot()
            self.assertEqual(
                [item.text for item in about_root.findall("supportedVersions/li")],
                ["1.6"],
            )
            self.assertEqual(
                about_root.findtext("modDependencies/li/packageId"),
                "author.example",
            )

    def test_excludes_other_game_versions(self):
        with tempfile.TemporaryDirectory() as temp:
            source = os.path.join(temp, "SourceMod")
            output = os.path.join(temp, "OutputTranslation")
            os.makedirs(source)
            self._write(source, "About/About.xml", "<ModMetaData><name>Versioned</name><packageId>a.v</packageId></ModMetaData>")
            for version in ("1.5", "1.6"):
                self._write(
                    source, version + "/Defs/Things.xml",
                    "<Defs><ThingDef><defName>Thing" + version.replace(".", "")
                    + "</defName><label>label " + version + "</label></ThingDef></Defs>",
                )
            csv_path = os.path.join(temp, "translations.csv")
            self._write_csv(csv_path, [
                ["1.5/Defs/Things.xml", "label", "//label", "label 1.5", "старое", "NEW", ""],
                ["1.6/Defs/Things.xml", "label", "//label", "label 1.6", "новое", "NEW", ""],
            ])
            result = build_translation_package(source, csv_path, output, "Russian", "1.6")
            self.assertEqual(result["entries"], 1)
            translated = ET.parse(
                os.path.join(output, "Languages", "Russian", "DefInjected", "ThingDef", "Things.xml")
            ).getroot()
            self.assertIsNone(translated.find("Thing15.label"))
            self.assertEqual(translated.findtext("Thing16.label"), "новое")

    def test_declared_compatibility_does_not_change_source_version(self):
        with tempfile.TemporaryDirectory() as temp:
            source = os.path.join(temp, "SourceMod")
            self._write(
                source, "About/About.xml",
                "<ModMetaData><name>Versioned</name><packageId>a.v</packageId>"
                "<supportedVersions><li>1.2</li><li>1.3</li><li>1.6</li>"
                "</supportedVersions></ModMetaData>",
            )
            rows = []
            for version in ("1.2", "1.3"):
                path = version + "/Defs/Things.xml"
                self._write(
                    source, path,
                    "<Defs><ThingDef><defName>SameThing</defName><label>label "
                    + version + "</label></ThingDef></Defs>",
                )
                rows.append([path, "label", "//label", "label " + version,
                             "translation " + version, "NEW", ""])
            self._write(
                source, "Defs/Common.xml",
                "<Defs><ThingDef><defName>Common</defName><label>common label"
                "</label></ThingDef></Defs>",
            )
            rows.append(["Defs/Common.xml", "label", "//label", "common label",
                         "common translation", "NEW", ""])
            csv_path = os.path.join(temp, "translations.csv")
            self._write_csv(csv_path, rows)

            for index, (declared, expected) in enumerate((
                (" 1.2, 1.3, 1.2 ", ["1.2", "1.3"]),
                ("1.3", ["1.3"]),
            )):
                with self.subTest(declared=declared):
                    output = os.path.join(temp, "Output" + str(index))
                    result = build_translation_package(
                        source, csv_path, output, "Russian", "1.2",
                        compatible_versions=declared,
                    )
                    self.assertEqual(result["entries"], 2)
                    self.assertEqual(result["unmatched"], 0)
                    about = ET.parse(os.path.join(output, "About", "About.xml")).getroot()
                    self.assertEqual(
                        [item.text for item in about.findall("supportedVersions/li")],
                        expected,
                    )
                    language_dir = os.path.join(
                        output, "Languages", "Russian", "DefInjected", "ThingDef"
                    )
                    versioned = ET.parse(os.path.join(language_dir, "Things.xml")).getroot()
                    self.assertEqual(versioned.findtext("SameThing.label"), "translation 1.2")
                    common = ET.parse(os.path.join(language_dir, "Common.xml")).getroot()
                    self.assertEqual(common.findtext("Common.label"), "common translation")
                    with open(os.path.join(output, "Generation report.txt"), encoding="utf-8") as f:
                        report = f.read()
                    self.assertIn("Source RimWorld version: 1.2", report)
                    self.assertIn("Declared compatible versions: " + ", ".join(expected), report)
                    self.assertIn("not verified by the translator", report)

    def test_invalid_versions_are_rejected_before_output_is_created(self):
        with tempfile.TemporaryDirectory() as temp:
            for source_version, declared in (("1.2, 1.3", "1.2"),
                                             ("1.2", "1.2,invalid"),
                                             ("1.2", "")):
                with self.subTest(source=source_version, declared=declared):
                    output = os.path.join(temp, "Output")
                    with self.assertRaises(ValueError):
                        build_translation_package(
                            temp, os.path.join(temp, "missing.csv"), output,
                            "Russian", source_version, compatible_versions=declared,
                        )
                    self.assertFalse(os.path.exists(output))

    def test_skips_translation_with_broken_placeholders(self):
        with tempfile.TemporaryDirectory() as temp:
            source = os.path.join(temp, "SourceMod")
            output = os.path.join(temp, "OutputTranslation")
            os.makedirs(source)
            self._write(source, "About/About.xml", "<ModMetaData><name>Safe</name><packageId>a.safe</packageId></ModMetaData>")
            self._write(
                source, "Defs/Things.xml",
                "<Defs><ThingDef><defName>SafeThing</defName>"
                "<description>Use {0}</description></ThingDef></Defs>",
            )
            csv_path = os.path.join(temp, "translations.csv")
            self._write_csv(csv_path, [[
                "Defs/Things.xml", "description", "//description",
                "Use {0}", "Использовать", "NEW", "",
            ]])
            result = build_translation_package(source, csv_path, output, "Russian", "1.6")
            self.assertEqual(result["entries"], 0)
            self.assertEqual(result["placeholder_mismatches"], 1)

    def test_versioned_definition_overrides_root_definition(self):
        with tempfile.TemporaryDirectory() as temp:
            source = os.path.join(temp, "SourceMod")
            output = os.path.join(temp, "OutputTranslation")
            os.makedirs(source)
            self._write(source, "About/About.xml", "<ModMetaData><name>Override</name><packageId>a.override</packageId></ModMetaData>")
            self._write(
                source, "Defs/Things.xml",
                "<Defs><ThingDef><defName>SameThing</defName><label>root label</label></ThingDef></Defs>",
            )
            self._write(
                source, "1.6/Defs/Things.xml",
                "<Defs><ThingDef><defName>SameThing</defName><label>version label</label></ThingDef></Defs>",
            )
            csv_path = os.path.join(temp, "translations.csv")
            self._write_csv(csv_path, [
                ["Defs/Things.xml", "label", "//label", "root label", "корень", "NEW", ""],
                ["1.6/Defs/Things.xml", "label", "//label", "version label", "версия", "NEW", ""],
            ])
            build_translation_package(source, csv_path, output, "Russian", "1.6")
            translated = ET.parse(
                os.path.join(output, "Languages", "Russian", "DefInjected", "ThingDef", "Things.xml")
            ).getroot()
            self.assertEqual(translated.findtext("SameThing.label"), "версия")


class BuildDialogTests(unittest.TestCase):
    def test_dialog_passes_source_and_compatibility_separately(self):
        with tempfile.TemporaryDirectory() as temp:
            app = Mock()
            app.source_dir.get.return_value = temp
            app.t.side_effect = lambda key, *args, **kwargs: key
            csv_path = os.path.join(temp, "translations.csv")
            with patch("rimworld_translator.filedialog.askopenfilename", return_value=csv_path), \
                 patch("rimworld_translator.simpledialog.askstring",
                       side_effect=["Russian", " 1.2 ", "1.2, 1.3"]) as ask, \
                 patch("rimworld_translator.filedialog.askdirectory", return_value=temp), \
                 patch("rimworld_translator.messagebox.showinfo"), \
                 patch("rimworld_translator.messagebox.showerror") as error, \
                 patch("rimworld_translator.build_translation_package") as build:
                build.return_value = {
                    "entries": 1, "files": 1, "unmatched": 0, "warnings": [],
                }
                RimWorldTranslator.build_translation_mod(app)
                self.assertEqual(ask.call_count, 3)
                self.assertEqual(ask.call_args_list[2][1]["initialvalue"], "1.2")
                self.assertEqual(build.call_args[0][-1], "1.2")
                self.assertEqual(build.call_args[1], {"compatible_versions": "1.2, 1.3"})
                error.assert_not_called()

    def test_cancelled_or_invalid_compatibility_does_not_build(self):
        with tempfile.TemporaryDirectory() as temp:
            for declared in (None, "", "1.2, invalid"):
                with self.subTest(declared=declared):
                    app = Mock()
                    app.source_dir.get.return_value = temp
                    app.t.side_effect = lambda key, *args, **kwargs: key
                    with patch("rimworld_translator.filedialog.askopenfilename",
                               return_value="translations.csv"), \
                         patch("rimworld_translator.simpledialog.askstring",
                               side_effect=["Russian", "1.2", declared]), \
                         patch("rimworld_translator.messagebox.showerror") as error, \
                         patch("rimworld_translator.filedialog.askdirectory") as output, \
                         patch("rimworld_translator.build_translation_package") as build:
                        RimWorldTranslator.build_translation_mod(app)
                        build.assert_not_called()
                        output.assert_not_called()
                        self.assertEqual(error.call_count, 0 if declared is None else 1)


if __name__ == "__main__":
    unittest.main()
