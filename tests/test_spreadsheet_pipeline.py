from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from document_pipeline import (  # noqa: E402
    detect_direction,
    finalize,
    normalize_text,
    prepare,
    read_json,
    sha256_text,
    write_json,
)
from spreadsheet_pipeline import (  # noqa: E402
    extract_xlsx_units,
    parse_xml,
    shared_strings_root,
    string_node_text,
    workbook_sheet_parts,
    workbook_structure,
    wrapped_style_indices,
)


CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>
"""

PACKAGE_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""

WORKBOOK = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Overview" sheetId="1" r:id="rId1"/>
    <sheet name="Hidden Terms" sheetId="2" state="hidden" r:id="rId2"/>
  </sheets>
</workbook>
"""

WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
</Relationships>
"""

STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font><sz val="11"/><name val="Aptos"/></font>
    <font><b/><color rgb="FFFFFFFF"/><sz val="12"/><name val="Aptos Display"/></font>
  </fonts>
  <fills count="3">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF1F4E78"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="2">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"><alignment vertical="center"/></xf>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"><alignment horizontal="center" vertical="center"/></xf>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>
"""

SHARED_STRINGS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="5" uniqueCount="5">
  <si><t>Project Status</t></si>
  <si><t>Clinical trial protocol</t></si>
  <si><t>项目 Project Status</t></si>
  <si><r><rPr><b/><color rgb="FF1F4E78"/></rPr><t>Quality </t></r><r><t>control</t></r></si>
  <si><t>监管要求</t></si>
</sst>
"""

SHEET1 = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="A1:B5"/>
  <cols><col min="1" max="1" width="28" customWidth="1"/><col min="2" max="2" width="16" customWidth="1"/></cols>
  <sheetData>
    <row r="1" ht="24" customHeight="1"><c r="A1" s="1" t="s"><v>0</v></c></row>
    <row r="2" ht="18" customHeight="1"><c r="A2" s="0" t="s"><v>1</v></c><c r="B2" s="0" t="n"><v>12</v></c></row>
    <row r="3"><c r="A3" s="0" t="inlineStr"><is><t>患者安全</t></is></c><c r="B3" s="0"><f>B2*2</f><v>24</v></c></row>
    <row r="4"><c r="A4" s="0" t="s"><v>2</v></c></row>
    <row r="5"><c r="A5" s="0" t="s"><v>3</v></c></row>
  </sheetData>
  <mergeCells count="1"><mergeCell ref="A1:B1"/></mergeCells>
  <conditionalFormatting sqref="B2:B3"><cfRule type="cellIs" dxfId="0" operator="greaterThan"><formula>10</formula></cfRule></conditionalFormatting>
  <dataValidations count="1"><dataValidation type="whole" operator="between" allowBlank="1" sqref="B2"><formula1>0</formula1><formula2>100</formula2></dataValidation></dataValidations>
  <hyperlinks><hyperlink ref="A4" location="'Hidden Terms'!A1" display="Open terms"/></hyperlinks>
</worksheet>
"""

SHEET2 = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="A1"/>
  <sheetData><row r="1"><c r="A1" s="0" t="s"><v>4</v></c></row></sheetData>
</worksheet>
"""


def write_fixture(path: Path, *, macro_enabled: bool = False) -> None:
    content_types = CONTENT_TYPES
    workbook_rels = WORKBOOK_RELS
    if macro_enabled:
        content_types = content_types.replace(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
            "application/vnd.ms-excel.sheet.macroEnabled.main+xml",
        ).replace(
            "</Types>",
            '  <Override PartName="/xl/vbaProject.bin" ContentType="application/vnd.ms-office.vbaProject"/>\n</Types>',
        )
        workbook_rels = workbook_rels.replace(
            "</Relationships>",
            '  <Relationship Id="rId5" Type="http://schemas.microsoft.com/office/2006/relationships/vbaProject" Target="vbaProject.bin"/>\n</Relationships>',
        )
    parts = {
        "[Content_Types].xml": content_types,
        "_rels/.rels": PACKAGE_RELS,
        "xl/workbook.xml": WORKBOOK,
        "xl/_rels/workbook.xml.rels": workbook_rels,
        "xl/styles.xml": STYLES,
        "xl/sharedStrings.xml": SHARED_STRINGS,
        "xl/worksheets/sheet1.xml": SHEET1,
        "xl/worksheets/sheet2.xml": SHEET2,
    }
    if macro_enabled:
        parts["xl/vbaProject.bin"] = b"test-vba-project-bytes"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)


def workbook_text_map(path: Path) -> dict[str, str]:
    units = extract_xlsx_units(path, lambda _: "keep", normalize_text, sha256_text)
    return {unit["id"]: unit["text"] for unit in units}


class SpreadsheetPipelineTests(unittest.TestCase):
    def test_full_pipeline_places_translation_in_same_cell(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "Clinical Workbook.xlsx"
            work = temp / "work"
            output_root = temp / "Output Files"
            write_fixture(source)
            original_structure = workbook_structure(source)

            prepare(argparse.Namespace(input=str(source), work_dir=str(work)))
            units = [
                json.loads(line)
                for line in (work / "units.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            translatable = [unit for unit in units if unit["translatable"]]
            ids_by_text = {unit["text"]: unit["id"] for unit in translatable}
            self.assertEqual(
                set(ids_by_text),
                {
                    "Project Status",
                    "Clinical trial protocol",
                    "患者安全",
                    "Quality control",
                    "监管要求",
                },
            )
            hidden = next(unit for unit in units if unit["text"] == "监管要求")
            self.assertEqual(hidden["sheet_state"], "hidden")

            targets = {
                "Project Status": "项目状态",
                "Clinical trial protocol": "临床试验方案",
                "患者安全": "Patient safety",
                "Quality control": "质量控制",
                "监管要求": "Regulatory requirements",
            }
            translations = {
                ids_by_text[source_text]: target
                for source_text, target in targets.items()
            }
            state = read_json(work / "state.json")
            state.update(
                {
                    "phase": "review",
                    "analysis_done": list(translations),
                    "translation_done": list(translations),
                    "review_done": list(translations),
                    "glossary_locked": True,
                    "translations": translations,
                }
            )
            write_json(work / "state.json", state)
            with (work / "glossary.csv").open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(["source", "target"])
                writer.writerow(["Clinical trial", "临床试验"])

            finalize(
                argparse.Namespace(
                    work_dir=str(work),
                    output_dir=str(output_root),
                    flat_output=False,
                    pdf=False,
                )
            )

            output_dir = output_root / "Clinical Workbook"
            workbook = output_dir / "Clinical Workbook.bilingual.xlsx"
            self.assertTrue(workbook.is_file())
            self.assertTrue((output_dir / "Clinical Workbook.glossary.csv").is_file())
            qa = read_json(output_dir / "Clinical Workbook.qa.json")
            self.assertTrue(qa["passed"])
            self.assertTrue(qa["same_cell_bilingual"])
            self.assertEqual(qa["not_wrapped"], [])
            self.assertEqual(workbook_structure(workbook), original_structure)

            texts = workbook_text_map(workbook)
            for source_text, target in targets.items():
                self.assertEqual(
                    texts[ids_by_text[source_text]],
                    f"{source_text}\n{target}",
                )
            bilingual_id = next(unit["id"] for unit in units if unit["text"] == "项目 Project Status")
            self.assertEqual(texts[bilingual_id], "项目 Project Status")

            with zipfile.ZipFile(workbook) as archive:
                sheets = workbook_sheet_parts(archive)
                self.assertEqual(
                    [(sheet["name"], sheet["state"]) for sheet in sheets],
                    [("Overview", "visible"), ("Hidden Terms", "hidden")],
                )
                overview = parse_xml(archive.read("xl/worksheets/sheet1.xml"))
                formula = overview.find(
                    ".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c[@r='B3']/"
                    "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}f"
                )
                self.assertEqual(formula.text, "B2*2")
                wrapped = wrapped_style_indices(archive)
                translated_cells = overview.xpath(
                    ".//s:c[@r='A1' or @r='A2' or @r='A3' or @r='A5']",
                    namespaces={
                        "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
                    },
                )
                self.assertTrue(all(int(cell.get("s", "0")) in wrapped for cell in translated_cells))

                shared_root, shared_items = shared_strings_root(archive)
                self.assertIsNotNone(shared_root)
                rich_values = [item for item in shared_items if string_node_text(item) == "Quality control\n质量控制"]
                self.assertEqual(len(rich_values), 1)
                translated_run = rich_values[0].findall(
                    "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}r"
                )[-1]
                self.assertIsNotNone(
                    translated_run.find(
                        "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}rPr"
                    )
                )

    def test_excel_pdf_export_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "input.xlsx"
            work = temp / "work"
            write_fixture(source)
            prepare(argparse.Namespace(input=str(source), work_dir=str(work)))
            units = [
                json.loads(line)
                for line in (work / "units.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            translations = {
                unit["id"]: "translated"
                for unit in units
                if unit["translatable"]
            }
            state = read_json(work / "state.json")
            state["translations"] = translations
            write_json(work / "state.json", state)
            with self.assertRaises(SystemExit):
                finalize(
                    argparse.Namespace(
                        work_dir=str(work),
                        output_dir=str(temp / "output"),
                        flat_output=False,
                        pdf=True,
                    )
                )

    def test_xlsm_vba_package_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "Macro Workbook.xlsm"
            work = temp / "work"
            output_root = temp / "Output Files"
            write_fixture(source, macro_enabled=True)
            prepare(argparse.Namespace(input=str(source), work_dir=str(work)))
            units = [
                json.loads(line)
                for line in (work / "units.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            translations = {
                unit["id"]: "translated"
                for unit in units
                if unit["translatable"]
            }
            state = read_json(work / "state.json")
            state["translations"] = translations
            write_json(work / "state.json", state)
            finalize(
                argparse.Namespace(
                    work_dir=str(work),
                    output_dir=str(output_root),
                    flat_output=False,
                    pdf=False,
                )
            )
            output = output_root / "Macro Workbook/Macro Workbook.bilingual.xlsm"
            with zipfile.ZipFile(source) as before, zipfile.ZipFile(output) as after:
                self.assertEqual(
                    before.read("xl/vbaProject.bin"),
                    after.read("xl/vbaProject.bin"),
                )
                self.assertIn(
                    b"application/vnd.ms-excel.sheet.macroEnabled.main+xml",
                    after.read("[Content_Types].xml"),
                )


if __name__ == "__main__":
    unittest.main()
