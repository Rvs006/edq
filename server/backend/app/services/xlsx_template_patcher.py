"""ZIP-level XLSX template patcher.

Patches cell values directly in the worksheet XML inside the .xlsx ZIP
archive, preserving ALL template assets byte-for-byte (images, drawings,
printer settings, custom XML, styles, themes, relationships, etc.).

Uses inline strings (``t="inlineStr"``) so the shared-strings table
(``xl/sharedStrings.xml``) is never touched.
"""

from __future__ import annotations

import logging
import mimetypes
import posixpath
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lxml import etree

logger = logging.getLogger(__name__)

# OOXML SpreadsheetML namespace
_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_PKG_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
_NS_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
_NS_XDR = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
_NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_NSMAP = {"": _NS}
_EMU_PER_PIXEL = 9525
_DRAWING_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing"
_IMAGE_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
_DRAWING_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.drawing+xml"

# Excel hard limit for cell text length
_MAX_CELL_LENGTH = 32_767

# Regex to split a cell reference like "G7" or "AA123" into (col_letters, row_number)
_CELL_REF_RE = re.compile(r"^([A-Z]+)(\d+)$", re.IGNORECASE)


@dataclass(frozen=True)
class XlsxImageInsert:
    sheet_name: str
    image_path: Path
    cell: str = "A1"
    width_px: int = 190
    height_px: int = 35
    description: str = "Report logo"


@dataclass
class _PlannedImageInsert:
    sheet_xml_path: str
    sheet_rels_path: str
    drawing_path: str
    drawing_rels_path: str
    media_path: str
    image_bytes: bytes
    cell: str
    width_px: int
    height_px: int
    description: str
    image_rel_id: str
    sheet_drawing_rel_id: str | None = None


def _col_to_index(col: str) -> int:
    """Convert a column letter (A, B, ..., Z, AA, AB, ...) to a 1-based index."""
    index = 0
    for ch in col.upper():
        index = index * 26 + (ord(ch) - ord("A") + 1)
    return index


def _next_numbered_part(existing_names: set[str], prefix: str, suffix: str) -> str:
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+){re.escape(suffix)}$")
    max_index = 0
    for name in existing_names:
        match = pattern.match(name)
        if match:
            max_index = max(max_index, int(match.group(1)))
    return f"{prefix}{max_index + 1}{suffix}"


def _rels_path_for_part(part_path: str) -> str:
    return posixpath.join(
        posixpath.dirname(part_path),
        "_rels",
        f"{posixpath.basename(part_path)}.rels",
    )


def _resolve_related_part(source_part_path: str, target: str) -> str:
    return posixpath.normpath(posixpath.join(posixpath.dirname(source_part_path), target))


def _relative_target(from_part_path: str, target_part_path: str) -> str:
    return posixpath.relpath(target_part_path, posixpath.dirname(from_part_path))


def _new_relationships_root() -> Any:
    return etree.Element(f"{{{_NS_PKG_RELS}}}Relationships", nsmap={None: _NS_PKG_RELS})


def _parse_relationships(data: bytes | None) -> Any:
    return etree.fromstring(data) if data else _new_relationships_root()


def _relationship_target(root: Any, rel_id: str) -> str | None:
    for rel in root.findall(f"{{{_NS_PKG_RELS}}}Relationship"):
        if rel.get("Id") == rel_id:
            return rel.get("Target")
    return None


def _add_relationship(root: Any, rel_id: str, rel_type: str, target: str) -> None:
    rel = etree.SubElement(root, f"{{{_NS_PKG_RELS}}}Relationship")
    rel.set("Id", rel_id)
    rel.set("Type", rel_type)
    rel.set("Target", target)


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


def _sheet_drawing_part(
    zf: zipfile.ZipFile,
    sheet_xml_path: str,
) -> tuple[str | None, str | None, str | None]:
    sheet_xml = zf.read(sheet_xml_path)
    sheet_root = etree.fromstring(sheet_xml)
    drawing_el = sheet_root.find(f"{{{_NS}}}drawing")
    if drawing_el is None:
        return None, None, None

    rel_id = drawing_el.get(f"{{{_NS_R}}}id")
    if not rel_id:
        return None, None, None

    sheet_rels_path = _rels_path_for_part(sheet_xml_path)
    if sheet_rels_path not in zf.namelist():
        return None, None, None

    sheet_rels = _parse_relationships(zf.read(sheet_rels_path))
    target = _relationship_target(sheet_rels, rel_id)
    if not target:
        return None, None, None

    return _resolve_related_part(sheet_xml_path, target), sheet_rels_path, rel_id


def _image_content_type(ext: str) -> str:
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    return mimetypes.types_map.get(ext, "image/png")


def _plan_image_inserts(
    zf: zipfile.ZipFile,
    sheet_paths: dict[str, str],
    image_inserts: list[XlsxImageInsert],
) -> list[_PlannedImageInsert]:
    if not image_inserts:
        return []

    names = set(zf.namelist())
    planned_names: set[str] = set()
    planned_sheet_drawings: dict[str, tuple[str, str, str | None]] = {}
    used_rel_ids: dict[str, set[str]] = {}
    plans: list[_PlannedImageInsert] = []

    def reserve_rel_id(rels_path: str) -> str:
        root = (
            _parse_relationships(zf.read(rels_path))
            if rels_path in names
            else _new_relationships_root()
        )
        used = used_rel_ids.setdefault(rels_path, set())
        max_index = 0
        for rel in root.findall(f"{{{_NS_PKG_RELS}}}Relationship"):
            rel_id = rel.get("Id", "")
            match = re.match(r"^rId(\d+)$", rel_id)
            if match:
                max_index = max(max_index, int(match.group(1)))
        for rel_id in used:
            match = re.match(r"^rId(\d+)$", rel_id)
            if match:
                max_index = max(max_index, int(match.group(1)))
        rel_id = f"rId{max_index + 1}"
        used.add(rel_id)
        return rel_id

    for insert in image_inserts:
        sheet_xml_path = sheet_paths.get(insert.sheet_name)
        if sheet_xml_path is None:
            logger.warning(
                "Sheet %r not found for image insert; available: %s",
                insert.sheet_name,
                list(sheet_paths.keys()),
            )
            continue

        image_path = Path(insert.image_path)
        if not image_path.exists():
            logger.warning("Image insert skipped; file not found: %s", image_path)
            continue

        extension = image_path.suffix.lower()
        if extension not in {".png", ".jpg", ".jpeg"}:
            logger.warning("Image insert skipped; unsupported extension: %s", image_path)
            continue

        if sheet_xml_path in planned_sheet_drawings:
            drawing_path, sheet_rels_path, sheet_drawing_rel_id = planned_sheet_drawings[sheet_xml_path]
        else:
            existing_drawing_path, sheet_rels_path, _ = _sheet_drawing_part(zf, sheet_xml_path)
            sheet_drawing_rel_id = None
            if existing_drawing_path:
                drawing_path = existing_drawing_path
            else:
                drawing_name = _next_numbered_part(
                    {posixpath.basename(name) for name in names | planned_names if name.startswith("xl/drawings/")},
                    "drawing",
                    ".xml",
                )
                drawing_path = f"xl/drawings/{drawing_name}"
                planned_names.add(drawing_path)
                sheet_rels_path = _rels_path_for_part(sheet_xml_path)
                sheet_drawing_rel_id = reserve_rel_id(sheet_rels_path)
            planned_sheet_drawings[sheet_xml_path] = (
                drawing_path,
                sheet_rels_path or _rels_path_for_part(sheet_xml_path),
                sheet_drawing_rel_id,
            )

        drawing_rels_path = _rels_path_for_part(drawing_path)
        image_rel_id = reserve_rel_id(drawing_rels_path)

        media_name = _next_numbered_part(
            {posixpath.basename(name) for name in names | planned_names if name.startswith("xl/media/")},
            "image",
            extension,
        )
        media_path = f"xl/media/{media_name}"
        planned_names.add(media_path)

        plans.append(
            _PlannedImageInsert(
                sheet_xml_path=sheet_xml_path,
                sheet_rels_path=sheet_rels_path or _rels_path_for_part(sheet_xml_path),
                drawing_path=drawing_path,
                drawing_rels_path=drawing_rels_path,
                media_path=media_path,
                image_bytes=image_path.read_bytes(),
                cell=insert.cell,
                width_px=insert.width_px,
                height_px=insert.height_px,
                description=insert.description,
                image_rel_id=image_rel_id,
                sheet_drawing_rel_id=sheet_drawing_rel_id,
            )
        )

    return plans


def _patch_sheet_drawing_reference(xml_bytes: bytes, rel_id: str | None) -> bytes:
    if not rel_id:
        return xml_bytes

    root = etree.fromstring(xml_bytes)
    drawing_el = root.find(f"{{{_NS}}}drawing")
    if drawing_el is None:
        drawing_el = etree.Element(f"{{{_NS}}}drawing")
        drawing_el.set(f"{{{_NS_R}}}id", rel_id)
        sheet_data = root.find(f"{{{_NS}}}sheetData")
        if sheet_data is not None:
            root.insert(list(root).index(sheet_data) + 1, drawing_el)
        else:
            root.append(drawing_el)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _max_picture_id(root: Any) -> int:
    max_id = 0
    for element in root.iter():
        if element.tag.endswith("}cNvPr"):
            raw_id = element.get("id")
            if raw_id and raw_id.isdigit():
                max_id = max(max_id, int(raw_id))
    return max_id


def _append_image_anchor(root: Any, plan: _PlannedImageInsert) -> None:
    row_num, _, col_idx = _parse_cell_ref(plan.cell)
    pic_id = _max_picture_id(root) + 1
    cx = max(plan.width_px, 1) * _EMU_PER_PIXEL
    cy = max(plan.height_px, 1) * _EMU_PER_PIXEL

    anchor = etree.SubElement(root, f"{{{_NS_XDR}}}oneCellAnchor")
    from_el = etree.SubElement(anchor, f"{{{_NS_XDR}}}from")
    etree.SubElement(from_el, f"{{{_NS_XDR}}}col").text = str(max(col_idx - 1, 0))
    etree.SubElement(from_el, f"{{{_NS_XDR}}}colOff").text = "0"
    etree.SubElement(from_el, f"{{{_NS_XDR}}}row").text = str(max(row_num - 1, 0))
    etree.SubElement(from_el, f"{{{_NS_XDR}}}rowOff").text = "0"
    ext_el = etree.SubElement(anchor, f"{{{_NS_XDR}}}ext")
    ext_el.set("cx", str(cx))
    ext_el.set("cy", str(cy))

    pic = etree.SubElement(anchor, f"{{{_NS_XDR}}}pic")
    nv_pic_pr = etree.SubElement(pic, f"{{{_NS_XDR}}}nvPicPr")
    c_nv_pr = etree.SubElement(nv_pic_pr, f"{{{_NS_XDR}}}cNvPr")
    c_nv_pr.set("id", str(pic_id))
    c_nv_pr.set("name", plan.description)
    c_nv_pr.set("descr", plan.description)
    etree.SubElement(nv_pic_pr, f"{{{_NS_XDR}}}cNvPicPr")

    blip_fill = etree.SubElement(pic, f"{{{_NS_XDR}}}blipFill")
    blip = etree.SubElement(blip_fill, f"{{{_NS_A}}}blip")
    blip.set(f"{{{_NS_R}}}embed", plan.image_rel_id)
    stretch = etree.SubElement(blip_fill, f"{{{_NS_A}}}stretch")
    etree.SubElement(stretch, f"{{{_NS_A}}}fillRect")

    sp_pr = etree.SubElement(pic, f"{{{_NS_XDR}}}spPr")
    xfrm = etree.SubElement(sp_pr, f"{{{_NS_A}}}xfrm")
    off = etree.SubElement(xfrm, f"{{{_NS_A}}}off")
    off.set("x", "0")
    off.set("y", "0")
    ext = etree.SubElement(xfrm, f"{{{_NS_A}}}ext")
    ext.set("cx", str(cx))
    ext.set("cy", str(cy))
    prst = etree.SubElement(sp_pr, f"{{{_NS_A}}}prstGeom")
    prst.set("prst", "rect")
    etree.SubElement(prst, f"{{{_NS_A}}}avLst")
    etree.SubElement(anchor, f"{{{_NS_XDR}}}clientData")


def _new_drawing_root() -> Any:
    return etree.Element(
        f"{{{_NS_XDR}}}wsDr",
        nsmap={"xdr": _NS_XDR, "a": _NS_A, "r": _NS_R},
    )


def _patch_drawing_xml(
    xml_bytes: bytes | None,
    plans: list[_PlannedImageInsert],
) -> bytes:
    root = etree.fromstring(xml_bytes) if xml_bytes else _new_drawing_root()
    for plan in plans:
        _append_image_anchor(root, plan)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _patch_rels_xml(
    xml_bytes: bytes | None,
    additions: list[tuple[str, str, str]],
) -> bytes:
    root = _parse_relationships(xml_bytes)
    existing_ids = {rel.get("Id") for rel in root.findall(f"{{{_NS_PKG_RELS}}}Relationship")}
    for rel_id, rel_type, target in additions:
        if rel_id not in existing_ids:
            _add_relationship(root, rel_id, rel_type, target)
            existing_ids.add(rel_id)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _patch_content_types(xml_bytes: bytes, plans: list[_PlannedImageInsert]) -> bytes:
    if not plans:
        return xml_bytes
    root = etree.fromstring(xml_bytes)
    existing_defaults = {
        node.get("Extension")
        for node in root.findall(f"{{{_NS_CT}}}Default")
    }
    existing_overrides = {
        node.get("PartName")
        for node in root.findall(f"{{{_NS_CT}}}Override")
    }

    for plan in plans:
        ext = Path(plan.media_path).suffix.lower().lstrip(".")
        if ext not in existing_defaults:
            default = etree.SubElement(root, f"{{{_NS_CT}}}Default")
            default.set("Extension", ext)
            default.set("ContentType", _image_content_type(f".{ext}"))
            existing_defaults.add(ext)

        part_name = f"/{plan.drawing_path}"
        if part_name not in existing_overrides:
            override = etree.SubElement(root, f"{{{_NS_CT}}}Override")
            override.set("PartName", part_name)
            override.set("ContentType", _DRAWING_CONTENT_TYPE)
            existing_overrides.add(part_name)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


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

        _refresh_row_spans(row_el)

    _refresh_sheet_dimension(root, sheet_data)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _refresh_row_spans(row_el: Any) -> None:
    """Recompute the `spans` attribute on a row after cell inserts.

    Excel flags a cell at column 8 inside a row declared ``spans="2:7"``
    and raises the "We found a problem with some content" repair dialog.
    Expand the upper bound to cover every cell currently on the row.
    """
    cols = []
    for c in row_el.findall(f"{{{_NS}}}c"):
        ref = c.get("r", "")
        m = _CELL_REF_RE.match(ref)
        if m:
            cols.append(_col_to_index(m.group(1).upper()))
    if not cols:
        return
    low = min(cols)
    high = max(cols)
    existing = row_el.get("spans")
    if existing and ":" in existing:
        try:
            e_low, e_high = (int(x) for x in existing.split(":", 1))
            low = min(low, e_low)
            high = max(high, e_high)
        except ValueError:
            pass
    row_el.set("spans", f"{low}:{high}")


def _refresh_sheet_dimension(root: Any, sheet_data: Any) -> None:
    """Recompute `<dimension ref="A1:Zn"/>` to cover all cells in sheetData.

    Excel compares the declared dimension against actual cell references.
    Writes beyond the declared range trigger repair dialogs on open.
    """
    dim = root.find(f"{{{_NS}}}dimension")
    if dim is None:
        return

    min_col = min_row = None
    max_col = max_row = 0
    for c in sheet_data.iter(f"{{{_NS}}}c"):
        ref = c.get("r", "")
        m = _CELL_REF_RE.match(ref)
        if not m:
            continue
        col_idx = _col_to_index(m.group(1).upper())
        row_idx = int(m.group(2))
        if min_col is None or col_idx < min_col:
            min_col = col_idx
        if min_row is None or row_idx < min_row:
            min_row = row_idx
        if col_idx > max_col:
            max_col = col_idx
        if row_idx > max_row:
            max_row = row_idx

    if min_col is None:
        return

    existing = dim.get("ref", "")
    m = re.match(r"^([A-Z]+)(\d+):([A-Z]+)(\d+)$", existing)
    if m:
        e_min_col = _col_to_index(m.group(1))
        e_min_row = int(m.group(2))
        e_max_col = _col_to_index(m.group(3))
        e_max_row = int(m.group(4))
        min_col = min(min_col, e_min_col)
        min_row = min(min_row, e_min_row)
        max_col = max(max_col, e_max_col)
        max_row = max(max_row, e_max_row)

    dim.set("ref", f"{_index_to_col(min_col)}{min_row}:{_index_to_col(max_col)}{max_row}")


def _index_to_col(idx: int) -> str:
    """Convert 1-based column index to letter (1 -> A, 26 -> Z, 27 -> AA)."""
    letters = ""
    n = idx
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters


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


_STRAY_ENTRY_PREFIXES = ("[trash]/", "[Trash]/", "trash/")


def _is_stray_zip_entry(name: str) -> bool:
    """Detect ZIP entries that are not part of the OOXML package.

    Excel leaves a ``[trash]/`` folder inside saved workbooks containing
    deleted-cell metadata. These entries are not declared in
    ``[Content_Types].xml`` and trigger Excel's "We found a problem with
    some content" repair dialog on open. Strip them during patching.
    """
    return any(name.startswith(p) for p in _STRAY_ENTRY_PREFIXES)


def patch_xlsx(
    template_path: Path,
    output_path: Path,
    sheet_updates: dict[str, dict[str, str | None]],
    image_inserts: list[XlsxImageInsert] | None = None,
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
        image_plans = _plan_image_inserts(src_zip, sheet_paths, image_inserts or [])

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

        plans_by_sheet_xml: dict[str, list[_PlannedImageInsert]] = {}
        plans_by_drawing: dict[str, list[_PlannedImageInsert]] = {}
        plans_by_drawing_rels: dict[str, list[_PlannedImageInsert]] = {}
        plans_by_sheet_rels: dict[str, list[_PlannedImageInsert]] = {}
        for plan in image_plans:
            plans_by_sheet_xml.setdefault(plan.sheet_xml_path, []).append(plan)
            plans_by_drawing.setdefault(plan.drawing_path, []).append(plan)
            plans_by_drawing_rels.setdefault(plan.drawing_rels_path, []).append(plan)
            if plan.sheet_drawing_rel_id:
                plans_by_sheet_rels.setdefault(plan.sheet_rels_path, []).append(plan)

        # Write to temp file for atomicity, then rename
        tmp_fd, tmp_path = tempfile.mkstemp(
            suffix=".xlsx",
            dir=str(output_path.parent),
        )

        try:
            with zipfile.ZipFile(tmp_path, "w") as dst_zip:
                written: set[str] = set()
                for item in src_zip.infolist():
                    if _is_stray_zip_entry(item.filename):
                        logger.info("Stripping stray entry %s", item.filename)
                        continue
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
                    if item.filename in plans_by_sheet_xml:
                        rel_id = next(
                            (
                                plan.sheet_drawing_rel_id
                                for plan in plans_by_sheet_xml[item.filename]
                                if plan.sheet_drawing_rel_id
                            ),
                            None,
                        )
                        data = _patch_sheet_drawing_reference(data, rel_id)
                    if item.filename in plans_by_drawing:
                        data = _patch_drawing_xml(data, plans_by_drawing[item.filename])
                    if item.filename in plans_by_drawing_rels:
                        data = _patch_rels_xml(
                            data,
                            [
                                (
                                    plan.image_rel_id,
                                    _IMAGE_REL_TYPE,
                                    _relative_target(plan.drawing_path, plan.media_path),
                                )
                                for plan in plans_by_drawing_rels[item.filename]
                            ],
                        )
                    if item.filename in plans_by_sheet_rels:
                        data = _patch_rels_xml(
                            data,
                            [
                                (
                                    plan.sheet_drawing_rel_id or "",
                                    _DRAWING_REL_TYPE,
                                    _relative_target(plan.sheet_xml_path, plan.drawing_path),
                                )
                                for plan in plans_by_sheet_rels[item.filename]
                                if plan.sheet_drawing_rel_id
                            ],
                        )
                    if item.filename == "[Content_Types].xml":
                        data = _patch_content_types(data, image_plans)

                    if (
                        item.filename in xml_to_updates
                        or item.filename in plans_by_sheet_xml
                        or item.filename in plans_by_drawing
                        or item.filename in plans_by_drawing_rels
                        or item.filename in plans_by_sheet_rels
                        or item.filename == "[Content_Types].xml"
                    ):
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
                    written.add(item.filename)

                for path, plans in plans_by_drawing.items():
                    if path not in written:
                        dst_zip.writestr(path, _patch_drawing_xml(None, plans))
                        written.add(path)

                for path, plans in plans_by_drawing_rels.items():
                    if path not in written:
                        dst_zip.writestr(
                            path,
                            _patch_rels_xml(
                                None,
                                [
                                    (
                                        plan.image_rel_id,
                                        _IMAGE_REL_TYPE,
                                        _relative_target(plan.drawing_path, plan.media_path),
                                    )
                                    for plan in plans
                                ],
                            ),
                        )
                        written.add(path)

                for path, plans in plans_by_sheet_rels.items():
                    if path not in written:
                        dst_zip.writestr(
                            path,
                            _patch_rels_xml(
                                None,
                                [
                                    (
                                        plan.sheet_drawing_rel_id or "",
                                        _DRAWING_REL_TYPE,
                                        _relative_target(plan.sheet_xml_path, plan.drawing_path),
                                    )
                                    for plan in plans
                                    if plan.sheet_drawing_rel_id
                                ],
                            ),
                        )
                        written.add(path)

                for plan in image_plans:
                    if plan.media_path not in written:
                        dst_zip.writestr(plan.media_path, plan.image_bytes)
                        written.add(plan.media_path)

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
