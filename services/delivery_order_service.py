# kalyn/services/delivery_order_service.py

import os
from typing import List

from dotenv import load_dotenv

from domain.models import DeliveryOrder, DeliveryOrderLine
from google_client import get_drive_service, get_docs_service
from services.doc_service import generate_delivery_order_doc, generate_barcode_do_doc
from utils.formatting import format_rupiah

from services.barcode_service import get_barcode_url_list


def build_delivery_order_from_rows(
        outlet_name: str,
        order_rows: List[dict],
) -> DeliveryOrder:
    """
    Build a DeliveryOrder domain object from a list of UI order rows.

    Each order row is expected to look like:
      {
        "SKU": str,
        "Size": str,
        "Item": str,
        "Category": str,
        "Color": str,
        "Quantity": int,
        "Unit Price": int,
        "Total": int,
      }
    """
    lines: List[DeliveryOrderLine] = []
    grand_total = 0

    for idx, row in enumerate(order_rows, start=1):
        qty = int(row["Quantity"])
        if qty <= 0:
            continue

        unit_price = int(row["Unit Price"] or 0)
        line_total = unit_price * qty
        grand_total += line_total

        label = f"T005-{row['Category']}-{row['Item']}"

        line = DeliveryOrderLine(
            index=idx,
            label=label,
            sku=row["SKU"],
            color=row["Color"],
            size=row["Size"] or "-",
            qty=qty,
            unit_price=unit_price,
            unit_price_display=format_rupiah(unit_price),
            line_total=line_total,
            line_total_display=format_rupiah(line_total),
        )
        lines.append(line)

    return DeliveryOrder(
        outlet_name=outlet_name,
        lines=lines,
        grand_total=grand_total,
        barcodes=[]
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_documents_for_delivery_order(
        delivery_order: DeliveryOrder,
) -> dict[str, str]:
    """
    Generate both:
      - Delivery Order docx
      - Barcode labels docx

    Returns:
      {
        "do_path": "/abs/path/to/Surat Jalan ... .docx",
        "barcode_path": "/abs/path/to/Barcode ... .docx",
      }
    """
    load_dotenv()
    template_do_doc_id = os.getenv("TEMPLATE_DO_DOC_ID")
    template_barcode_doc_id = os.getenv("TEMPLATE_BARCODE_DOC_ID")

    docs_url = {
        "do_path": "",
        "barcode_path": "",
    }

    outlet_dir = {
        "Banda": ['1q-APtN37mwMl7O3IVWMKurEI7ZL_2i8S', '1-uSGu3KXngnPGWMpc1Ij4exVQ2Z4k6Mz'],
        "Karawang": ['1DUdTQKvuv4GRtjojnmHW_3BQoyyA_DCx', '1ZkTX_Uf0LgFufD4X2kz2pWWygMpHjKfj'],
        "Purwakarta": ['14ssRFy2VeBGqWJk6ahayMLX5GGhGwApM', '14TNK9i9u423-X2LC3hu6bKz7wBDhT0nF'],
    }

    drive = get_drive_service()
    docs = get_docs_service()

    do_doc_dir = outlet_dir[delivery_order.outlet_name][0]
    barcode_doc_dir = outlet_dir[delivery_order.outlet_name][1]
    delivery_order.barcodes = get_barcode_url_list(delivery_order, drive)
    docs_url["do_path"] = generate_delivery_order_doc(docs, drive, template_do_doc_id, do_doc_dir, delivery_order)
    docs_url["barcode_path"] = generate_barcode_do_doc(docs, drive, template_barcode_doc_id, barcode_doc_dir,
                                                       delivery_order)

    return docs_url

    # os.makedirs(output_dir, exist_ok=True)
    #
    # timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # safe_outlet = delivery_order.outlet_name.replace(" ", "_")
    #
    # do_filename = f"Surat Jalan - Kalyn - {safe_outlet} - {timestamp}.docx"
    # barcode_filename = f"Barcode - Kalyn - {safe_outlet} - {timestamp}.docx"
    #
    # do_path = os.path.join(output_dir, do_filename)
    # barcode_path = os.path.join(output_dir, barcode_filename)
    #
    # _create_delivery_order_doc(delivery_order, do_path)
    # _create_barcode_doc(delivery_order, barcode_path)
    #
    # return {
    #     "do_path": os.path.abspath(do_path),
    #     "barcode_path": os.path.abspath(barcode_path),
    # }
