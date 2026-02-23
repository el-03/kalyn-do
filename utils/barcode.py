# kalyn/utils/barcode.py

import os
from pathlib import Path

from barcode import Code128
from barcode.writer import ImageWriter

# Folder to store generated barcode images
BARCODE_IMG_DIR = Path("barcodes")
BARCODE_IMG_DIR.mkdir(parents=True, exist_ok=True)


def ensure_barcode_image(barcode_text: str) -> str:
    """
    Generate a Code128 barcode image for `barcode_text` if it doesn't exist yet.
    Returns the absolute path to the PNG file.
    """
    filename = BARCODE_IMG_DIR / f"{barcode_text}.png"
    if filename.exists():
        return str(filename)

    # python-barcode will append '.png' if path has no extension
    code = Code128(barcode_text, writer=ImageWriter())
    full = Path(code.save(str(filename)[:-4]))  # remove ".png" when calling save

    if full != filename:
        # normalize name
        if full.exists():
            full.rename(filename)

    return str(filename)