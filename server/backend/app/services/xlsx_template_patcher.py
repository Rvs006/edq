"""ZIP-level XLSX template patcher.

Patches cell values directly in the worksheet XML inside the .xlsx ZIP
archive, preserving ALL template assets byte-for-byte (images, drawings,
printer settings, custom XML, styles, themes, relationships, etc.).

Uses inline strings (``t="inlineStr"``) so the shared-strings table
(``xl/sharedStrings.xml``) is never touched.
"""

from __future__ import annotations

import logging
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

logger = logging.getLogger(__name__)

# OOXML SpreadsheetML namespace
_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_PKG_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
_NSMAP = {"": _NS}

# Excel hard limit for cell text length
_MAX_CELL_LENGTH = 32_767

# Regex to split a cell reference like "G7" or "AA123" into (col_letters, row_number)
_CELL_REF_RE = re.compile(r"^([A-Z]+)(\d+)$", re.IGNORECASE)


def _col_to_index(col: str) -> int:
    """Convert a column letter (A, B, ..., Z, AA, AB, ...) to a 1-based index."""
    index = 0
    for ch in col.upper():
        index = index * 26 + (ord(ch) - ord("A") + 1)
    return index


def _parse_cell_ref(ref: str) -> tuple[int, str, int]:
    """Parse ``"G7"`` into ``(row=7, col_letter="G", col_index=7)``."""
    m = _CELL_REF_RE.match(ref.strip())
    if not m:
        raise ValueError(f"Invalid cell reference: {ref!r}")
    col_letter = m.group(1).upper()
    row_num = int(m.group(2))
    return row_num, col_letter, _col_to_index(col_letter)


def _resolve_sheet_paths(zf: zipfile.ZipFile) -> dict[str, str]:
    """Map sheet display names to their ZIP-internal XML paths.

    Parses ``xl/workbook.xml`` for sheet name → rId, then
    ``xl/_rels/workbook.xml.rels`` for rId → target path.
    """
    # Parse workbook.xml to get sheet name → rId
    wb_xml = zf.read("xl/workbook.xml")
    wb_root = etree.fromstring(wb_xml)

    sheets_el = wb_root.find(f"{{{_NS}}}sheets")
    if sheets_el is None:
        raise ValueError("Cannot find <sheets> in xl/workbook.xml")

    name_to_rid: dict[str, str] = {}
    for sheet_el in sheets_el.findall(f"{{{_NS}}}sheet"):
        name = sheet_el.get("name", "")
        rid = sheet_el.get(f"{{{_NS_R}}}id", "")
        if name and rid:
            name_to_rid[name] = rid

    # Parse workbook.xml.rels to get rId → target
    rels_xml = zf.read("xl/_rels/workbook.xml.rels")
    rels_root = etree.fromstring(rels_xml)

    rid_to_target: dict[str, str] = {}
    for rel in rels_root.findall(f"{{{_NS_PKG_RELS}}}Relationship"):
        rid = rel.get("Id", "")
        target = rel.get("Target", "")
        if rid and target:
            rid_to_target[rid] = target

    # Combine: name → full zip path
    result: dict[str, str] = {}
    for name, rid in name_to_rid.items():
        target = rid_to_target.get(rid)
        if target:
            # Targets are relative to xl/, e.g. "worksheets/sheet1.xml"
            full_path = f"xl/{target}" if not target.startswith("xl/") else target
            result[name] = full_path

    return result


def _patch_sheet_xml(xml_bytes: bytes, cell_updates: dict[str, str | None]) -> bytes:
    """Patch specific cell values in a worksheet XML.

    Uses inline strings (``t="inlineStr"`` + ``<is><t>value</t></is>``)
    to avoid touching the shared-strings table.  Preserves the ``s``
    (style index) attribute on every cell so formatting stays intact.

    Parameters
    ----------
    xml_bytes:
        Raw XML bytes of the worksheet (e.g. ``xl/worksheets/sheet1.xml``).
    cell_updates:
        Mapping of cell references to new string values.
        ``{"G7": "some value", "F11": "PASS", "G12": None}``
        A ``None`` or empty-string value clears the cell content but
        keeps the style.
    """
    root = etree.fromstring(xml_bytes)

    sheet_data = root.find(f"{{{_NS}}}sheetData")
    if sheet_data is None:
        raise ValueError("Cannot find <sheetData> in worksheet XML")

    # Pre-parse all updates
    parsed: list[tuple[int, str, int, str | None]] = []
    for ref, value in cell_updates.items():
        row_num, col_letter, col_idx = _parse_cell_ref(ref)
        # Truncate oversized values
        if value and len(value) > _MAX_CELL_LENGTH:
            logger.warning(
                "Cell %s value truncated from %d to %d chars",
                ref, len(value), _MAX_CELL_LENGTH,
            )
            value = value[:_MAX_CELL_LENGTH]
        parsed.append((row_num, col_letter, col_idx, value))

    # Group updates by row
    rows_updates: dict[int, list[tuple[str, int, str | None]]] = {}
    for row_num, col_letter, col_idx, value in parsed:
        rows_updates.setdefault(row_num, []).append((col_letter, col_idx, value))

    # Sort each row's updates by column index for correct insertion order
    for row_num in rows_updates:
        rows_updates[row_num].sort(key=lambda x: x[1])

    # Build index of existing <row> elements
    existing_rows: dict[int, Any] = {}
    for row_el in sheet_data.findall(f"{{{_NS}}}row"):
        r = row_el.get("r")
        if r and r.isdigit():
            existing_rows[int(r)] = row_el

    for row_num, updates in sorted(rows_updates.items()):
        row_el = existing_rows.get(row_num)

        if row_el is None:
            # Create <row> in correct position
            row_el = etree.SubElement(sheet_data, f"{{{_NS}}}row")
            row_el.set("r", str(row_num))
            # Insert in sorted row order
            _insert_row_sorted(sheet_data, row_el, row_num)
            existing_rows[row_num] = row_el

        for col_letter, col_idx, value in updates:
            cell_ref = f"{col_letter}{row_num}"
            _set_cell_value(row_el, cell_ref, col_idx, value)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _insert_row_sorted(sheet_data: Any, new_row: Any, row_num: int) -> None:
    """Insert a <row> element at the correct position within <sheetData>."""
    # Remove from current position (SubElement appends at end)
    sheet_data.remove(new_row)

    inserted = False
    for idx, child in enumerate(sheet_data):
        if child.tag == f"{{{_NS}}}row":
            r = child.get("r")
            if r and r.isdigit() and int(r) > row_num:
                sheet_data.insert(idx, new_row)
                inserted = True
                break

    if not inserted:
        sheet_data.append(new_row)


def _set_cell_value(
    row_el: Any,
    cell_ref: str,
    col_idx: int,
    value: str | None,
) -> None:
    """Set or clear a cell value within a <row> element.

    Preserves the ``s`` (style) attribute.  Uses ``inlineStr`` type.
    Inserts new ``<c>`` elements in strict column order (Excel requirement).
    """
    # Find existing <c> for this reference
    cell_el = None
    for c in row_el.findall(f"{{{_NS}}}c"):
        if c.get("r") == cell_ref:
            cell_el = c
            break

    if cell_el is None:
        # Create <c> element in correct column order
        cell_el = etree.Element(f"{{{_NS}}}c")
        cell_el.set("r", cell_ref)
        _insert_cell_sorted(row_el, cell_el, col_idx)

    # Clear existing value children (<v>, <is>, <f>)
    for child_tag in (f"{{{_NS}}}v", f"{{{_NS}}}is", f"{{{_NS}}}f"):
        for child in cell_el.findall(child_tag):
            cell_el.remove(child)

    if value is not None and value != "":
        # Set as inline string
        cell_el.set("t", "inlineStr")
        is_el = etree.SubElement(cell_el, f"{{{_NS}}}is")
        t_el = etree.SubElement(is_el, f"{{{_NS}}}t")
        t_el.text = value
        # Preserve whitespace
        t_el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    else:
        # Clear: remove type attribute but keep style
        if "t" in cell_el.attrib:
            del cell_el.attrib["t"]


def _insert_cell_sorted(row_el: Any, new_cell: Any, col_idx: int) -> None:
    """Insert a <c> element at the correct column position within a <row>.

    Excel requires <c> elements in strict alphabetical column order.
    Violating this causes file corruption.
    """
    inserted = False
    for idx, child in enumerate(row_el):
        if child.tag == f"{{{_NS}}}c":
            child_ref = child.get("r", "")
            m = _CELL_REF_RE.match(child_ref)
            if m:
                existing_col_idx = _col_to_index(m.group(1).upper())
                if existing_col_idx > col_idx:
                    row_el.insert(idx, new_cell)
                    inserted = True
                    break

    if not inserted:
        row_el.append(new_cell)


def patch_xlsx(
    template_path: Path,
    output_path: Path,
    sheet_updates: dict[str, dict[str, str | None]],
) -> Path:
    """Create a patched copy of an XLSX template.

    Copies the template ZIP byte-for-byte, only modifying the specific
    worksheet XMLs that have cell updates.  All other ZIP entries (images,
    drawings, printer settings, custom XML, styles, themes, relationships)
    are preserved identically.

    Parameters
    ----------
    template_path:
        Path to the original .xlsx template file.
    output_path:
        Path for the output .xlsx file.
    sheet_updates:
        Nested dict: ``{sheet_name: {cell_ref: value, ...}, ...}``
        Example::

            {
                "TEST SUMMARY": {"G7": "1", "G8": "01/04/2025 - 02/04/2025"},
                "TESTPLAN": {"F11": "PASS", "G11": "Device connected OK"},
            }

    Returns
    -------
    Path
        The output file path.
    """
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(str(template_path), "r") as src_zip:
        # Resolve sheet names to their XML paths
        sheet_paths = _resolve_sheet_paths(src_zip)

        # Map XML paths → sheet updates
        xml_to_updates: dict[str, dict[str, str | None]] = {}
        for sheet_name, updates in sheet_updates.items():
            xml_path = sheet_paths.get(sheet_name)
            if xml_path is None:
                logger.warning(
                    "Sheet %r not found in template; available: %s",
                    sheet_name,
                    list(sheet_paths.keys()),
                )
                continue
            if updates:
                xml_to_updates[xml_path] = updates

        # Write to temp file for atomicity, then rename
        tmp_fd, tmp_path = tempfile.mkstemp(
            suffix=".xlsx",
            dir=str(output_path.parent),
        )

        try:
            with zipfile.ZipFile(tmp_path, "w") as dst_zip:
                for item in src_zip.infolist():
                    data = src_zip.read(item.filename)

                    if item.filename in xml_to_updates:
                        # Patch this sheet's XML
                        updates = xml_to_updates[item.filename]
                        logger.info(
                            "Patching %s: %d cell(s)",
                            item.filename,
                            len(updates),
                        )
                        data = _patch_sheet_xml(data, updates)
                        # Write with same compression but let Python
                        # recalculate size/CRC for the modified data
                        dst_zip.writestr(
                            item.filename,
                            data,
                            compress_type=item.compress_type,
                        )
                    else:
                        # Copy byte-for-byte preserving original ZipInfo
                        dst_zip.writestr(item, data)

            # Atomic rename
            import os

            os.close(tmp_fd)
            tmp_fd = -1
            # On Windows, target must not exist for rename
            if output_path.exists():
                output_path.unlink()
            Path(tmp_path).rename(output_path)

        except Exception:
            # Clean up temp file on failure
            import os

            if tmp_fd >= 0:
                os.close(tmp_fd)
            if Path(tmp_path).exists():
                Path(tmp_path).unlink()
            raise

    logger.info("Patched XLSX written to %s", output_path)
    return output_path
