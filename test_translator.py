import csv
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET

from rimworld_translator import (
    build_translation_package,
    iter_def_translation_targets,
    load_existing_translations,
    mask_placeholders,
    RimWorldTranslator,
    safe_join,
    unmask_placeholders,
)


class TranslatorHelpersTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
