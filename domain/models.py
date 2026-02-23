# kalyn/domain/models.py

from dataclasses import dataclass
from typing import List


@dataclass
class BarcodeResult:
    file_id: str
    public_url: str


@dataclass
class DeliveryOrderLine:
    """
    Represents one line item in a delivery order.
    """
    index: int  # 1-based index in the document
    label: str  # e.g. "T005-Category-Item"
    sku: str  # barcode text (your item.sku)
    color: str
    size: str
    qty: int
    unit_price: int  # raw integer price
    unit_price_display: str  # formatted for human display
    line_total: int
    line_total_display: str  # formatted line total


@dataclass
class DeliveryOrder:
    """
    A complete delivery order for one destination store.
    """
    outlet_name: str  # e.g. "Banda"
    lines: List[DeliveryOrderLine]
    barcodes: List[BarcodeResult]
    grand_total: int  # raw integer
