import datetime
import math
from typing import List, Dict, Tuple

from dotenv import load_dotenv
from googleapiclient.discovery import Resource

from domain.models import DeliveryOrder, DeliveryOrderLine
from services.drive_service import ensure_file_public_and_get_url


def generate_delivery_order_doc(
        docs: Resource,
        drive: Resource,
        template_doc_id: str,
        target_folder_id: str,
        order: DeliveryOrder,
) -> str:
    """
    1. Copy the template doc into target folder
    2. Rename it with outlet_name + timestamp
    3. Replace placeholders based on DeliveryOrder
    4. Remove unused table rows (those still containing {{...}})

    Returns:
        new Google Docs documentId
    """

    # 1) Copy template into folder, with new name
    new_doc_id = _copy_template_to_folder(
        drive=drive,
        template_doc_id=template_doc_id,
        target_folder_id=target_folder_id,
        order=order,
    )

    # 2) Replace global placeholders
    _replace_global_placeholders(docs, new_doc_id, order)

    # 3) Per-line text + barcode placeholders
    _fill_lines_and_barcodes(docs, drive, new_doc_id, order)

    # 4) Delete unused rows that still contain placeholders like {{no_10}}
    _delete_unused_rows(docs, new_doc_id)

    return new_doc_id


# ---------- Step 1: copy + rename ----------

def _copy_template_to_folder(
        drive: Resource,
        template_doc_id: str,
        target_folder_id: str,
        order: DeliveryOrder,
) -> str:
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y%m%d-%H%M%S")
    new_name = f"{order.outlet_name}-{timestamp}"

    body = {
        "name": new_name,
        "parents": [target_folder_id],
    }

    copied = drive.files().copy(
        fileId=template_doc_id,
        body=body,
        fields="id",
    ).execute()

    return copied["id"]


# ---------- Step 2: global placeholders ----------

def _replace_global_placeholders(
        docs: Resource,
        document_id: str,
        order: DeliveryOrder,
) -> None:
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    store_location = order.outlet_name

    # if you want formatted grand_total, do it here
    total_sum = f"{order.grand_total:,}".replace(",", ".")  # e.g. 31.263

    replacements = {
        "{{date}}": today_str,
        "{{store_location}}": store_location,
        "{{total_sum}}": total_sum,
    }

    requests: List[Dict] = []
    for placeholder, value in replacements.items():
        requests.append(
            {
                "replaceAllText": {
                    "containsText": {
                        "text": placeholder,
                        "matchCase": True,
                    },
                    "replaceText": value,
                }
            }
        )

    if requests:
        docs.documents().batchUpdate(
            documentId=document_id,
            body={"requests": requests},
        ).execute()


# ---------- Step 3: lines + barcodes ----------

def _fill_lines_and_barcodes(
        docs: Resource,
        drive: Resource,
        document_id: str,
        order: DeliveryOrder,
) -> None:
    """
    For each DeliveryOrderLine (1-based index n), we replace:

      {{no_n}}        -> line.index (or n)
      {{cat_n}}       -> label
      {{color_n}}     -> color
      {{size_n}}      -> size
      {{harga_n}}     -> unit_price_display
      {{qty_n}}       -> qty
      {{harga_sum_n}} -> line_total_display

    And {{barcode_n}} is replaced by an inline image using the corresponding
    BarcodeResult at index n-1 (if present).
    """
    text_requests: List[Dict] = []

    for i, line in enumerate(order.lines, start=1):
        text_map = _build_line_placeholder_map(i, line)

        for placeholder, value in text_map.items():
            text_requests.append(
                {
                    "replaceAllText": {
                        "containsText": {
                            "text": placeholder,
                            "matchCase": True,
                        },
                        "replaceText": value,
                    }
                }
            )

    # First flush all text replacements
    if text_requests:
        docs.documents().batchUpdate(
            documentId=document_id,
            body={"requests": text_requests},
        ).execute()

    # Reload the doc for barcode insertion work
    doc = docs.documents().get(documentId=document_id).execute()

    # Collect all barcode replacement actions first
    barcode_actions: List[Tuple[int, int, str]] = []

    for i, _line in enumerate(order.lines, start=1):
        if i > len(order.barcodes):
            continue

        file_id = order.barcodes[i - 1].file_id
        image_url = ensure_file_public_and_get_url(drive, file_id)

        placeholder = f"{{{{barcode_{i}}}}}"
        occurrences = _find_text_occurrences(doc, placeholder)

        for start_index, end_index in occurrences:
            barcode_actions.append((start_index, end_index, image_url))

    if not barcode_actions:
        return

    # 🔑 Sort by start_index descending so deletions don't break later ranges
    barcode_actions.sort(key=lambda x: x[0], reverse=True)

    image_requests: List[Dict] = []

    for start_index, end_index, image_url in barcode_actions:
        # Delete the placeholder text
        image_requests.append(
            {
                "deleteContentRange": {
                    "range": {
                        "startIndex": start_index,
                        "endIndex": end_index,
                    }
                }
            }
        )
        # Insert the image at the same location
        image_requests.append(
            {
                "insertInlineImage": {
                    "location": {"index": start_index},
                    "uri": image_url,
                    "objectSize": {
                        "height": {"magnitude": 30, "unit": "PT"},
                        "width": {"magnitude": 100, "unit": "PT"},
                    },
                }
            }
        )

    docs.documents().batchUpdate(
        documentId=document_id,
        body={"requests": image_requests},
    ).execute()


def _build_line_placeholder_map(
        i: int,
        line: DeliveryOrderLine,
) -> Dict[str, str]:
    """
    Build mapping for a single line n = i:
      {{no_i}}, {{cat_i}}, {{color_i}}, {{size_i}},
      {{harga_i}}, {{qty_i}}, {{harga_sum_i}}
    Adjust {{qty_i}} -> {{jumlah_i}} here if your template uses that name.
    """
    return {
        f"{{{{no_{i}}}}}": str(line.index),
        f"{{{{cat_{i}}}}}": line.label,
        f"{{{{color_{i}}}}}": line.color,
        f"{{{{size_{i}}}}}": line.size,
        f"{{{{harga_{i}}}}}": line.unit_price_display,
        f"{{{{qty_{i}}}}}": str(line.qty),
        f"{{{{harga_sum_{i}}}}}": line.line_total_display,
    }


def _find_text_occurrences(doc: Dict, target: str) -> List[Tuple[int, int]]:
    """
    Walk the document and find all (startIndex, endIndex) ranges where `target`
    appears. This is needed so we can replace {{barcode_n}} with an inline image.
    """
    occurrences: List[Tuple[int, int]] = []

    def walk_elements(elements: List[Dict]):
        for elem in elements:
            if "paragraph" in elem:
                for run in elem["paragraph"].get("elements", []):
                    text_run = run.get("textRun")
                    if not text_run:
                        continue
                    content = text_run.get("content", "")
                    start_idx = run.get("startIndex")
                    if start_idx is None:
                        continue

                    offset = 0
                    while True:
                        pos = content.find(target, offset)
                        if pos == -1:
                            break
                        abs_start = start_idx + pos
                        abs_end = abs_start + len(target)
                        occurrences.append((abs_start, abs_end))
                        offset = pos + len(target)

            if "table" in elem:
                for row in elem["table"].get("tableRows", []):
                    for cell in row.get("tableCells", []):
                        walk_elements(cell.get("content", []))

            if "tableOfContents" in elem:
                walk_elements(elem["tableOfContents"].get("content", []))

    body = doc.get("body", {})
    content = body.get("content", [])
    walk_elements(content)
    return occurrences


# ---------- Step 4: delete unused rows ----------

def _delete_unused_rows(
        docs: Resource,
        document_id: str,
) -> None:
    """
    Delete table rows that still contain any '{{' after we finish doing replacements.
    That means those rows had no matching DeliveryOrderLine and should be removed.
    """

    doc = docs.documents().get(documentId=document_id).execute()
    body = doc.get("body", {})
    content = body.get("content", [])

    delete_requests: List[Dict] = []

    for elem in content:
        table = elem.get("table")
        if not table:
            continue

        # In Google Docs, we don't have tableId; we use tableStartLocation.index.
        table_start_index = elem.get("startIndex")
        if table_start_index is None:
            continue

        for row_idx, row in enumerate(table.get("tableRows", [])):
            row_text = _get_row_text(row)

            # any leftover placeholder → delete that row
            if "{{" in row_text:
                delete_requests.append(
                    {
                        "deleteTableRow": {
                            "tableCellLocation": {
                                "tableStartLocation": {
                                    "index": table_start_index
                                },
                                "rowIndex": row_idx,
                            }
                        }
                    }
                )

    # Important: delete rows from bottom to top so indices stay valid
    if delete_requests:
        delete_requests.reverse()
        docs.documents().batchUpdate(
            documentId=document_id,
            body={"requests": delete_requests},
        ).execute()


def _get_row_text(row: Dict) -> str:
    """Concatenate all text content in a table row (for placeholder detection)."""
    texts: List[str] = []

    for cell in row.get("tableCells", []):
        for elem in cell.get("content", []):
            para = elem.get("paragraph")
            if not para:
                continue
            for run in para.get("elements", []):
                text_run = run.get("textRun")
                if not text_run:
                    continue
                content = text_run.get("content", "")
                texts.append(content)

    return "".join(texts)


def generate_barcode_do_doc(
        docs: Resource,
        drive: Resource,
        template_doc_id: str,
        target_folder_id: str,
        order: DeliveryOrder,
        max_slots: int = 280,
) -> str:
    """
    Generate a barcode document for printing stickers.

    Rules:
      - Copy the template into target folder
      - Rename: "<store>-<timestamp>"
      - Flatten DeliveryOrder.lines by qty
      - For n from 1..total_items:
          {{cat_n}}   -> line.label
          {{price_n}} -> line.unit_price_display
          {{barcode_n}} -> barcode image for that line
      - Clear all remaining placeholders for n > total_items
    """
    # 1) Copy template into folder, with new name
    new_doc_id = _copy_barcode_template_to_folder(
        drive=drive,
        template_doc_id=template_doc_id,
        target_folder_id=target_folder_id,
        order=order,
    )

    # 2) Flatten lines by qty -> per-slot items
    items = _flatten_delivery_order_lines(order, max_slots=max_slots)

    # 3) Fill text placeholders (cat_n, price_n)
    _replace_barcode_text_placeholders(docs, new_doc_id, items)

    # 4) Replace {{barcode_n}} with inline images
    _replace_barcode_image_placeholders(docs, drive, new_doc_id, items)

    # 5) Clear unused placeholders in remaining slots
    _clear_unused_barcode_placeholders(docs, new_doc_id, used_slots=len(items), max_slots=max_slots)

    # 6) Delete unused rows
    _delete_unused_barcode_rows(docs, new_doc_id, used_slots=len(items))

    return new_doc_id


# ---------- copy & rename ----------

def _copy_barcode_template_to_folder(
        drive: Resource,
        template_doc_id: str,
        target_folder_id: str,
        order: DeliveryOrder,
) -> str:
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y%m%d-%H%M%S")
    new_name = f"BARCODE-{order.outlet_name}-{timestamp}"

    body = {
        "name": new_name,
        "parents": [target_folder_id],
    }

    copied = drive.files().copy(
        fileId=template_doc_id,
        body=body,
        fields="id",
        supportsAllDrives=True,
    ).execute()

    return copied["id"]


# ---------- flatten lines by qty ----------

def _flatten_delivery_order_lines(
        order: DeliveryOrder,
        max_slots: int,
) -> List[Tuple[DeliveryOrderLine, str]]:
    """
    Returns a flat list of (line, barcode_file_id) of length <= max_slots.

    If a line has qty=5, it appears 5 times.
    We assume order.barcodes[i] matches order.lines[i].
    """
    items: List[Tuple[DeliveryOrderLine, str]] = []

    for idx, line in enumerate(order.lines):
        barcode_file_id = None
        if idx < len(order.barcodes):
            barcode_file_id = order.barcodes[idx].file_id

        for _ in range(line.qty):
            if len(items) >= max_slots:
                return items
            items.append((line, barcode_file_id))

    return items


# ---------- text placeholders: {{cat_n}}, {{price_n}} ----------

def _replace_barcode_text_placeholders(
        docs: Resource,
        document_id: str,
        items: List[Tuple[DeliveryOrderLine, str]],
) -> None:
    """
    For slot n (1-based), replace:

      {{cat_n}}   -> line.label
      {{price_n}} -> line.unit_price_display

    If your template uses a different name (e.g. {{price_n}}),
    change the placeholder keys here.
    """
    requests: List[Dict] = []

    for slot_index, (line, _barcode_file_id) in enumerate(items, start=1):
        text_map = {
            f"{{{{cat_{slot_index}}}}}": line.label,
            f"{{{{price_{slot_index}}}}}": f"Rp {line.unit_price_display}",
        }

        for placeholder, value in text_map.items():
            requests.append(
                {
                    "replaceAllText": {
                        "containsText": {
                            "text": placeholder,
                            "matchCase": True,
                        },
                        "replaceText": value,
                    }
                }
            )

    if requests:
        docs.documents().batchUpdate(
            documentId=document_id,
            body={"requests": requests},
        ).execute()


# ---------- barcode images: {{barcode_n}} ----------

def _replace_barcode_image_placeholders(
        docs: Resource,
        drive: Resource,
        document_id: str,
        items: List[Tuple[DeliveryOrderLine, str]],
) -> None:
    """
    For slot n (1-based), {{barcode_n}} is replaced with an inline image
    for that slot's barcode file, if present.
    """
    if not items:
        return

    doc = docs.documents().get(documentId=document_id).execute()

    # Collect all barcode replacement actions first
    barcode_actions: List[Tuple[int, int, str]] = []

    for slot_index, (_line, barcode_file_id) in enumerate(items, start=1):
        if not barcode_file_id:
            continue

        image_url = ensure_file_public_and_get_url(drive, barcode_file_id)
        placeholder = f"{{{{barcode_{slot_index}}}}}"

        occurrences = _find_text_occurrences(doc, placeholder)
        for start_index, end_index in occurrences:
            barcode_actions.append((start_index, end_index, image_url))

    if not barcode_actions:
        return

    # Sort by start_index DESC so deletions don't break later ranges
    barcode_actions.sort(key=lambda x: x[0], reverse=True)

    image_requests: List[Dict] = []

    for start_index, end_index, image_url in barcode_actions:
        image_requests.append(
            {
                "deleteContentRange": {
                    "range": {
                        "startIndex": start_index,
                        "endIndex": end_index,
                    }
                }
            }
        )
        image_requests.append(
            {
                "insertInlineImage": {
                    "location": {"index": start_index},
                    "uri": image_url,
                    "objectSize": {
                        "height": {"magnitude": 30.0, "unit": "PT"},
                        "width": {"magnitude": 100.0, "unit": "PT"},
                    },
                }
            }
        )

    docs.documents().batchUpdate(
        documentId=document_id,
        body={"requests": image_requests},
    ).execute()


# ---------- clear unused placeholders ----------

def _clear_unused_barcode_placeholders(
        docs: Resource,
        document_id: str,
        used_slots: int,
        max_slots: int,
) -> None:
    """
    For slots n in (used_slots+1 .. max_slots), clear any leftover placeholders:
      {{cat_n}}, {{price_n}}, {{barcode_n}}
    """

    if used_slots >= max_slots:
        return

    requests: List[Dict] = []

    for slot_index in range(used_slots + 1, max_slots + 1):
        for placeholder in [
            f"{{{{cat_{slot_index}}}}}",
            f"{{{{price_{slot_index}}}}}",
            f"{{{{barcode_{slot_index}}}}}",
        ]:
            requests.append(
                {
                    "replaceAllText": {
                        "containsText": {
                            "text": placeholder,
                            "matchCase": True,
                        },
                        "replaceText": "",
                    }
                }
            )

    if requests:
        # You might want to chunk this if max_slots is huge, but 280 is fine in one go.
        docs.documents().batchUpdate(
            documentId=document_id,
            body={"requests": requests},
        ).execute()


# ---------- delete unused rows ----------

def _delete_unused_barcode_rows(
    docs: Resource,
    document_id: str,
    used_slots: int,
    cols_per_row: int = 7,
) -> None:
    """
    Slots ({{cat_1}}, {{cat_2}}, ...) are 1-based.
    Google Docs table rowIndex is 0-based.

    If used_slots = 10 and cols_per_row = 7:
        rows_needed = ceil(10 / 7) = 2
        Keep rows 0 and 1.
        Delete rows 2..N.
    """
    if used_slots <= 0:
        return

    rows_needed = math.ceil(used_slots / cols_per_row)

    doc = docs.documents().get(documentId=document_id).execute()
    body = doc.get("body", {})
    content = body.get("content", [])

    delete_requests: List[Dict] = []

    for elem in content:
        table = elem.get("table")
        if not table:
            continue

        table_start_index = elem.get("startIndex")
        if table_start_index is None:
            continue

        rows = table.get("tableRows", [])
        total_rows = len(rows)

        if rows_needed >= total_rows:
            continue  # nothing to delete

        # Delete rows from rows_needed to end (Docs rowIndex is 0-based)
        for row_idx in range(rows_needed, total_rows):
            delete_requests.append(
                {
                    "deleteTableRow": {
                        "tableCellLocation": {
                            "tableStartLocation": {
                                "index": table_start_index,
                            },
                            "rowIndex": row_idx,
                        }
                    }
                }
            )

    if delete_requests:
        # Delete bottom-up to keep indices stable
        delete_requests.reverse()
        docs.documents().batchUpdate(
            documentId=document_id,
            body={"requests": delete_requests},
        ).execute()