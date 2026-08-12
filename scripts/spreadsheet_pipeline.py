#!/usr/bin/env python3
"""Format-preserving XLSX/XLSM helpers for the bilingual translation pipeline."""

from __future__ import annotations

import hashlib
import posixpath
import shutil
import tempfile
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

try:
    from lxml import etree
except ImportError:  # pragma: no cover - checked by the caller
    etree = None


S_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
P_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
XML_NS = "http://www.w3.org/XML/1998/namespace"
S = f"{{{S_NS}}}"
P = f"{{{P_NS}}}"
SHEET_NS = {"s": S_NS, "r": R_NS}


def require_lxml() -> None:
    if etree is None:
        raise RuntimeError(
            "Missing dependency: lxml. Install scripts/requirements.txt "
            "before processing Excel files."
        )


def parse_xml(data: bytes) -> Any:
    require_lxml()
    return etree.fromstring(data)


def serialize_xml(root: Any) -> bytes:
    return etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )


def resolve_part(base_part: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(
        posixpath.join(posixpath.dirname(base_part), target)
    )


def workbook_sheet_parts(archive: zipfile.ZipFile) -> list[dict[str, str]]:
    workbook_part = "xl/workbook.xml"
    rels_part = "xl/_rels/workbook.xml.rels"
    workbook = parse_xml(archive.read(workbook_part))
    rels = parse_xml(archive.read(rels_part))
    targets = {
        rel.get("Id"): resolve_part(workbook_part, rel.get("Target", ""))
        for rel in rels.findall(f"{P}Relationship")
    }
    sheets: list[dict[str, str]] = []
    for sheet in workbook.xpath(".//s:sheets/s:sheet", namespaces=SHEET_NS):
        rel_id = sheet.get(f"{{{R_NS}}}id")
        part = targets.get(rel_id)
        if part:
            sheets.append(
                {
                    "name": sheet.get("name", ""),
                    "part": part,
                    "state": sheet.get("state", "visible"),
                }
            )
    return sheets


def shared_strings_root(
    archive: zipfile.ZipFile,
) -> tuple[Any | None, list[Any]]:
    part = "xl/sharedStrings.xml"
    if part not in archive.namelist():
        return None, []
    root = parse_xml(archive.read(part))
    return root, list(root.findall(f"{S}si"))


def string_node_text(node: Any) -> str:
    return "".join(text.text or "" for text in node.iter(f"{S}t"))


def cell_text(cell: Any, shared_items: list[Any]) -> str | None:
    if cell.find(f"{S}f") is not None:
        return None
    value_type = cell.get("t")
    if value_type == "s":
        value = cell.find(f"{S}v")
        if value is None or value.text is None:
            return None
        try:
            index = int(value.text)
        except ValueError:
            return None
        if index < 0 or index >= len(shared_items):
            return None
        return string_node_text(shared_items[index])
    if value_type == "inlineStr":
        inline = cell.find(f"{S}is")
        return string_node_text(inline) if inline is not None else None
    if value_type == "str":
        value = cell.find(f"{S}v")
        return value.text if value is not None else None
    return None


def extract_xlsx_units(
    workbook_path: Path,
    detect_direction: Callable[[str], str],
    normalize_text: Callable[[str], str],
    sha256_text: Callable[[str], str],
) -> list[dict[str, Any]]:
    require_lxml()
    units: list[dict[str, Any]] = []
    with zipfile.ZipFile(workbook_path) as archive:
        _, shared_items = shared_strings_root(archive)
        for sheet in workbook_sheet_parts(archive):
            root = parse_xml(archive.read(sheet["part"]))
            for order, cell in enumerate(root.xpath(".//s:sheetData/s:row/s:c", namespaces=SHEET_NS)):
                text = cell_text(cell, shared_items)
                if text is None:
                    continue
                clean = normalize_text(text)
                if not clean:
                    continue
                direction = detect_direction(clean)
                cell_ref = cell.get("r", "")
                units.append(
                    {
                        "id": f"{sheet['part']}:{cell_ref}",
                        "part": sheet["part"],
                        "sheet": sheet["name"],
                        "sheet_state": sheet["state"],
                        "cell": cell_ref,
                        "cell_order": order,
                        "kind": "cell",
                        "text": text,
                        "normalized_text": clean,
                        "source_hash": sha256_text(text),
                        "direction": direction,
                        "translatable": direction != "keep",
                    }
                )
    return units


def append_translation_to_string_node(node: Any, target: str) -> None:
    runs = node.findall(f"{S}r")
    if not runs:
        text_nodes = node.findall(f"{S}t")
        if text_nodes:
            text = text_nodes[-1]
            text.text = (text.text or "") + "\n" + target
            text.set(f"{{{XML_NS}}}space", "preserve")
            return
        text = etree.Element(f"{S}t")
        text.set(f"{{{XML_NS}}}space", "preserve")
        text.text = "\n" + target
        node.insert(0, text)
        return

    translated_run = etree.Element(f"{S}r")
    first_properties = runs[0].find(f"{S}rPr")
    if first_properties is not None:
        translated_run.append(deepcopy(first_properties))
    text = etree.SubElement(translated_run, f"{S}t")
    text.set(f"{{{XML_NS}}}space", "preserve")
    text.text = "\n" + target
    insert_at = len(node)
    for index, child in enumerate(node):
        if child.tag in {f"{S}rPh", f"{S}phoneticPr"}:
            insert_at = index
            break
    node.insert(insert_at, translated_run)


def replace_string_node_text(node: Any, target: str) -> None:
    """Replace visible text while retaining the source string's first run style."""
    runs = node.findall(f"{S}r")
    first_properties = runs[0].find(f"{S}rPr") if runs else None
    for child in list(node):
        if child.tag not in {f"{S}rPh", f"{S}phoneticPr"}:
            node.remove(child)
    if runs:
        run = etree.Element(f"{S}r")
        if first_properties is not None:
            run.append(deepcopy(first_properties))
        text = etree.SubElement(run, f"{S}t")
        text.text = target
        if target[:1].isspace() or target[-1:].isspace():
            text.set(f"{{{XML_NS}}}space", "preserve")
        node.insert(0, run)
    else:
        text = etree.Element(f"{S}t")
        text.text = target
        if target[:1].isspace() or target[-1:].isspace():
            text.set(f"{{{XML_NS}}}space", "preserve")
        node.insert(0, text)


def ensure_wrapped_style(
    cell: Any,
    styles_root: Any | None,
    style_cache: dict[int, int],
) -> None:
    if styles_root is None:
        return
    cell_xfs = styles_root.find(f"{S}cellXfs")
    if cell_xfs is None:
        return
    try:
        original_index = int(cell.get("s", "0"))
    except ValueError:
        original_index = 0
    styles = list(cell_xfs.findall(f"{S}xf"))
    if original_index < 0 or original_index >= len(styles):
        original_index = 0
    original = styles[original_index]
    alignment = original.find(f"{S}alignment")
    if alignment is not None and alignment.get("wrapText") in {"1", "true"}:
        return
    if original_index not in style_cache:
        wrapped = deepcopy(original)
        alignment = wrapped.find(f"{S}alignment")
        if alignment is None:
            alignment = etree.SubElement(wrapped, f"{S}alignment")
        alignment.set("wrapText", "1")
        wrapped.set("applyAlignment", "1")
        cell_xfs.append(wrapped)
        style_cache[original_index] = len(styles)
        cell_xfs.set("count", str(len(styles) + 1))
    cell.set("s", str(style_cache[original_index]))


def apply_translations_to_xlsx(
    source_workbook: Path,
    output_workbook: Path,
    units: list[dict[str, Any]],
    translations: dict[str, str],
) -> dict[str, Any]:
    require_lxml()
    temp = Path(tempfile.mkdtemp(prefix="bilingual-xlsx-"))
    try:
        with zipfile.ZipFile(source_workbook) as archive:
            archive.extractall(temp)

        shared_path = temp / "xl/sharedStrings.xml"
        if shared_path.exists():
            shared_root = etree.parse(
                str(shared_path),
                etree.XMLParser(remove_blank_text=False),
            ).getroot()
            shared_items = list(shared_root.findall(f"{S}si"))
        else:
            shared_root = None
            shared_items = []

        styles_path = temp / "xl/styles.xml"
        if styles_path.exists():
            styles_root = etree.parse(
                str(styles_path),
                etree.XMLParser(remove_blank_text=False),
            ).getroot()
        else:
            styles_root = None

        inserted = 0
        style_cache: dict[int, int] = {}
        by_part: dict[str, list[dict[str, Any]]] = {}
        for unit in units:
            if unit["id"] in translations:
                by_part.setdefault(unit["part"], []).append(unit)

        for part, part_units in by_part.items():
            path = temp / part
            root = etree.parse(
                str(path),
                etree.XMLParser(remove_blank_text=False),
            ).getroot()
            cells = {
                cell.get("r", ""): cell
                for cell in root.xpath(".//s:sheetData/s:row/s:c", namespaces=SHEET_NS)
            }
            for unit in part_units:
                cell = cells.get(unit["cell"])
                if cell is None:
                    continue
                current = cell_text(cell, shared_items)
                if current != unit["text"]:
                    continue
                target = translations[unit["id"]]
                value_type = cell.get("t")
                if value_type == "s":
                    value = cell.find(f"{S}v")
                    if value is None or value.text is None or shared_root is None:
                        continue
                    source_item = shared_items[int(value.text)]
                    bilingual_item = deepcopy(source_item)
                    append_translation_to_string_node(bilingual_item, target)
                    shared_root.append(bilingual_item)
                    shared_items.append(bilingual_item)
                    value.text = str(len(shared_items) - 1)
                    shared_root.set("uniqueCount", str(len(shared_items)))
                elif value_type == "inlineStr":
                    inline = cell.find(f"{S}is")
                    if inline is None:
                        continue
                    append_translation_to_string_node(inline, target)
                elif value_type == "str":
                    value = cell.find(f"{S}v")
                    if value is None:
                        continue
                    value.text = unit["text"] + "\n" + target
                else:
                    continue
                ensure_wrapped_style(cell, styles_root, style_cache)
                inserted += 1
            path.write_bytes(serialize_xml(root))

        if shared_root is not None:
            shared_path.write_bytes(serialize_xml(shared_root))
        if styles_root is not None:
            styles_path.write_bytes(serialize_xml(styles_root))

        output_workbook.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_workbook, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(temp.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(temp).as_posix())
        return {
            "inserted_translations": inserted,
            "requested_translations": len(translations),
            "same_cell_separator": "\\n",
        }
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def apply_replacements_to_xlsx(
    source_workbook: Path,
    output_workbook: Path,
    units: list[dict[str, Any]],
    replacements: dict[str, str],
) -> dict[str, Any]:
    """Create a translation-only workbook without changing cell styles/layout."""
    require_lxml()
    temp = Path(tempfile.mkdtemp(prefix="english-xlsx-"))
    try:
        with zipfile.ZipFile(source_workbook) as archive:
            archive.extractall(temp)
        shared_path = temp / "xl/sharedStrings.xml"
        if shared_path.exists():
            shared_root = etree.parse(
                str(shared_path),
                etree.XMLParser(remove_blank_text=False),
            ).getroot()
            shared_items = list(shared_root.findall(f"{S}si"))
        else:
            shared_root = None
            shared_items = []

        replaced = 0
        by_part: dict[str, list[dict[str, Any]]] = {}
        for unit in units:
            if unit["id"] in replacements:
                by_part.setdefault(unit["part"], []).append(unit)
        for part, part_units in by_part.items():
            path = temp / part
            root = etree.parse(
                str(path),
                etree.XMLParser(remove_blank_text=False),
            ).getroot()
            cells = {
                cell.get("r", ""): cell
                for cell in root.xpath(".//s:sheetData/s:row/s:c", namespaces=SHEET_NS)
            }
            for unit in part_units:
                cell = cells.get(unit["cell"])
                if cell is None or cell_text(cell, shared_items) != unit["text"]:
                    continue
                target = replacements[unit["id"]]
                value_type = cell.get("t")
                if value_type == "s":
                    value = cell.find(f"{S}v")
                    if value is None or value.text is None or shared_root is None:
                        continue
                    target_item = deepcopy(shared_items[int(value.text)])
                    replace_string_node_text(target_item, target)
                    shared_root.append(target_item)
                    shared_items.append(target_item)
                    value.text = str(len(shared_items) - 1)
                    shared_root.set("uniqueCount", str(len(shared_items)))
                elif value_type == "inlineStr":
                    inline = cell.find(f"{S}is")
                    if inline is None:
                        continue
                    replace_string_node_text(inline, target)
                elif value_type == "str":
                    value = cell.find(f"{S}v")
                    if value is None:
                        continue
                    value.text = target
                else:
                    continue
                replaced += 1
            path.write_bytes(serialize_xml(root))

        if shared_root is not None:
            shared_path.write_bytes(serialize_xml(shared_root))
        output_workbook.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_workbook, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(temp.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(temp).as_posix())
        return {
            "replaced_translations": replaced,
            "requested_replacements": len(replacements),
        }
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def workbook_structure(workbook_path: Path) -> dict[str, Any]:
    require_lxml()
    with zipfile.ZipFile(workbook_path) as archive:
        # ZIP directory entries are optional container metadata, not OOXML parts.
        # Some producers include them while deterministic re-packaging does not.
        names = [name for name in archive.namelist() if not name.endswith("/")]
        sheets = workbook_sheet_parts(archive)
        counts: dict[str, Any] = {
            "worksheets": len(sheets),
            "tables": sum(name.startswith("xl/tables/") for name in names),
            "drawings": sum(name.startswith("xl/drawings/") and name.endswith(".xml") for name in names),
            "charts": sum(name.startswith("xl/charts/") and name.endswith(".xml") for name in names),
            "media": sum(name.startswith("xl/media/") for name in names),
            "comments": sum("/comments" in name and name.endswith(".xml") for name in names),
            "external_links": sum(name.startswith("xl/externalLinks/") and name.endswith(".xml") for name in names),
            "vba_projects": sum(name.endswith("vbaProject.bin") for name in names),
            "merged_ranges": 0,
            "formulas": 0,
            "data_validations": 0,
            "conditional_formats": 0,
            "hyperlinks": 0,
            "sheet_names": [sheet["name"] for sheet in sheets],
        }
        formula_records: list[str] = []
        for sheet in sheets:
            root = parse_xml(archive.read(sheet["part"]))
            counts["merged_ranges"] += len(root.xpath(".//s:mergeCells/s:mergeCell", namespaces=SHEET_NS))
            counts["data_validations"] += len(root.xpath(".//s:dataValidations/s:dataValidation", namespaces=SHEET_NS))
            counts["conditional_formats"] += len(root.xpath(".//s:conditionalFormatting", namespaces=SHEET_NS))
            counts["hyperlinks"] += len(root.xpath(".//s:hyperlinks/s:hyperlink", namespaces=SHEET_NS))
            for cell in root.xpath(".//s:sheetData/s:row/s:c[s:f]", namespaces=SHEET_NS):
                formula = cell.find(f"{S}f")
                formula_records.append(
                    f"{sheet['part']}|{cell.get('r', '')}|{formula.text if formula is not None else ''}"
                )
        counts["formulas"] = len(formula_records)
        counts["formula_sha256"] = hashlib.sha256(
            "\n".join(formula_records).encode("utf-8")
        ).hexdigest()
        counts["package_parts_sha256"] = hashlib.sha256(
            "\n".join(sorted(names)).encode("utf-8")
        ).hexdigest()
        return counts


def wrapped_style_indices(archive: zipfile.ZipFile) -> set[int]:
    if "xl/styles.xml" not in archive.namelist():
        return set()
    root = parse_xml(archive.read("xl/styles.xml"))
    cell_xfs = root.find(f"{S}cellXfs")
    if cell_xfs is None:
        return set()
    wrapped: set[int] = set()
    for index, xf in enumerate(cell_xfs.findall(f"{S}xf")):
        alignment = xf.find(f"{S}alignment")
        if alignment is not None and alignment.get("wrapText") in {"1", "true"}:
            wrapped.add(index)
    return wrapped


def validate_xlsx_output(
    source_workbook: Path,
    output_workbook: Path,
    units: list[dict[str, Any]],
    translations: dict[str, str],
    normalize_text: Callable[[str], str],
) -> dict[str, Any]:
    require_lxml()
    output_units = extract_xlsx_units(
        output_workbook,
        lambda text: "keep",
        normalize_text,
        lambda text: "",
    )
    output_map = {unit["id"]: unit["text"] for unit in output_units}
    missing_original: list[str] = []
    missing_translation: list[str] = []
    changed_nontranslatable: list[str] = []
    for unit in units:
        output_text = output_map.get(unit["id"])
        if output_text is None:
            missing_original.append(unit["id"])
            continue
        if unit.get("bilingual_output", unit["translatable"]):
            expected = unit["text"] + "\n" + translations.get(unit["id"], "")
            if output_text != expected:
                missing_translation.append(unit["id"])
        elif output_text != unit["text"]:
            changed_nontranslatable.append(unit["id"])

    not_wrapped: list[str] = []
    with zipfile.ZipFile(output_workbook) as archive:
        _, shared_items = shared_strings_root(archive)
        wrapped_indices = wrapped_style_indices(archive)
        sheet_cells: dict[str, dict[str, Any]] = {}
        for sheet in workbook_sheet_parts(archive):
            root = parse_xml(archive.read(sheet["part"]))
            sheet_cells[sheet["part"]] = {
                cell.get("r", ""): cell
                for cell in root.xpath(".//s:sheetData/s:row/s:c", namespaces=SHEET_NS)
            }
        for unit in units:
            if not unit.get("bilingual_output", unit["translatable"]):
                continue
            cell = sheet_cells.get(unit["part"], {}).get(unit["cell"])
            if cell is None or cell_text(cell, shared_items) is None:
                continue
            try:
                style_index = int(cell.get("s", "0"))
            except ValueError:
                style_index = 0
            if style_index not in wrapped_indices:
                not_wrapped.append(unit["id"])

    before = workbook_structure(source_workbook)
    after = workbook_structure(output_workbook)
    structure_ok = before == after
    return {
        "original_units": len(units),
        "output_units": len(output_units),
        "missing_original": missing_original,
        "missing_translation": missing_translation,
        "changed_nontranslatable": changed_nontranslatable,
        "not_wrapped": not_wrapped,
        "structure_before": before,
        "structure_after": after,
        "structure_ok": structure_ok,
        "same_cell_bilingual": not missing_translation,
        "passed": (
            not missing_original
            and not missing_translation
            and not changed_nontranslatable
            and not not_wrapped
            and structure_ok
        ),
    }


def workbook_format_signature(workbook_path: Path) -> str:
    """Hash workbook layout/styles while ignoring translatable cell values."""
    require_lxml()
    records: list[bytes] = []
    with zipfile.ZipFile(workbook_path) as archive:
        for sheet in workbook_sheet_parts(archive):
            root = parse_xml(archive.read(sheet["part"]))
            for cell in root.xpath(".//s:sheetData/s:row/s:c", namespaces=SHEET_NS):
                if cell.find(f"{S}f") is not None:
                    continue
                for child in list(cell):
                    if child.tag in {f"{S}v", f"{S}is"}:
                        cell.remove(child)
            records.append(
                sheet["part"].encode("utf-8")
                + b"\0"
                + etree.tostring(root, method="c14n")
            )
        for part in ("xl/styles.xml", "xl/workbook.xml"):
            if part in archive.namelist():
                records.append(part.encode("utf-8") + b"\0" + archive.read(part))
    return hashlib.sha256(b"\n".join(records)).hexdigest()


def validate_replaced_xlsx_output(
    source_workbook: Path,
    output_workbook: Path,
    units: list[dict[str, Any]],
    replacements: dict[str, str],
    normalize_text: Callable[[str], str],
    cjk_count: Callable[[str], int],
) -> dict[str, Any]:
    output_units = extract_xlsx_units(
        output_workbook,
        lambda text: "keep",
        normalize_text,
        lambda text: "",
    )
    output_map = {unit["id"]: unit["text"] for unit in output_units}
    missing_units: list[str] = []
    incorrect_replacements: list[str] = []
    changed_preserved: list[str] = []
    residual_chinese_targets: list[str] = []
    for unit in units:
        output_text = output_map.get(unit["id"])
        if output_text is None:
            missing_units.append(unit["id"])
            continue
        if unit["id"] in replacements:
            target = replacements[unit["id"]]
            if output_text != target:
                incorrect_replacements.append(unit["id"])
            if cjk_count(target):
                residual_chinese_targets.append(unit["id"])
        elif output_text != unit["text"]:
            changed_preserved.append(unit["id"])
    before = workbook_structure(source_workbook)
    after = workbook_structure(output_workbook)
    structure_ok = before == after
    format_before = workbook_format_signature(source_workbook)
    format_after = workbook_format_signature(output_workbook)
    format_ok = format_before == format_after
    return {
        "required": True,
        "output_exists": output_workbook.is_file(),
        "requested_replacements": len(replacements),
        "missing_units": missing_units,
        "incorrect_replacements": incorrect_replacements,
        "changed_preserved": changed_preserved,
        "residual_chinese_targets": residual_chinese_targets,
        "structure_before": before,
        "structure_after": after,
        "structure_ok": structure_ok,
        "format_signature_before": format_before,
        "format_signature_after": format_after,
        "format_ok": format_ok,
        "passed": (
            output_workbook.is_file()
            and not missing_units
            and not incorrect_replacements
            and not changed_preserved
            and not residual_chinese_targets
            and structure_ok
            and format_ok
        ),
    }
