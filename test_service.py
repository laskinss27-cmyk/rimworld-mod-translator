import csv
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET

from translator_service import export_translations, import_into_original, inspect_mod


class TranslatorServiceTests(unittest.TestCase):
    def _write(self, root, relative, content):
        path = os.path.join(root, *relative.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as output:
            output.write(content)
        return path

    def test_inspection_and_export(self):
        with tempfile.TemporaryDirectory() as temp:
            source = os.path.join(temp, "Example")
            os.makedirs(source)
            self._write(
                source,
                "About/About.xml",
                "<ModMetaData><name>Example</name><packageId>author.example</packageId>"
                "<supportedVersions><li>1.6</li></supportedVersions></ModMetaData>",
            )
            self._write(
                source,
                "Defs/Things.xml",
                "<Defs><ThingDef><defName>ExampleThing</defName>"
                "<label>example thing</label><description>Uses {0} safely.</description>"
                "</ThingDef></Defs>",
            )
            csv_path = os.path.join(temp, "translations.csv")

            metadata = inspect_mod(source)
            result = export_translations(source, csv_path)

            self.assertEqual(metadata["name"], "Example")
            self.assertEqual(metadata["xml_count"], 1)
            self.assertEqual(result["rows"], 2)
            with open(csv_path, "r", encoding="utf-8-sig") as input_file:
                rows = list(csv.DictReader(input_file))
            self.assertEqual(rows[1]["Original Text"], "Uses __RWPH_0__ safely.")
            self.assertEqual(rows[1]["Placeholders"], "__RWPH_0__={0}")

    def test_legacy_import_creates_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            source = os.path.join(temp, "Example")
            os.makedirs(source)
            xml_path = self._write(
                source,
                "Defs/Things.xml",
                "<Defs><ThingDef><defName>ExampleThing</defName>"
                "<label>example thing</label></ThingDef></Defs>",
            )
            csv_path = os.path.join(temp, "translations.csv")
            with open(csv_path, "w", encoding="utf-8-sig", newline="") as output:
                writer = csv.writer(output)
                writer.writerow([
                    "File", "Tag", "XPath", "Original Text",
                    "Translation", "Status", "Placeholders",
                ])
                writer.writerow([
                    "Defs/Things.xml", "label", "//label",
                    "example thing", "пример", "DONE", "",
                ])

            result = import_into_original(source, csv_path)

            self.assertEqual(result["applied"], 1)
            self.assertTrue(os.path.isdir(result["backup"]))
            self.assertEqual(ET.parse(xml_path).getroot().findtext("ThingDef/label"), "пример")
            backup_xml = os.path.join(result["backup"], "Defs", "Things.xml")
            self.assertEqual(
                ET.parse(backup_xml).getroot().findtext("ThingDef/label"),
                "example thing",
            )


if __name__ == "__main__":
    unittest.main()
