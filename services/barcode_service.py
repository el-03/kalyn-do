# services/barcode_service.py
import os
from dotenv import load_dotenv
import io
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

from domain.models import DeliveryOrder, BarcodeResult
from .drive_service import (
    find_file_in_folder_by_name,
    upload_file_to_folder,
    ensure_file_public_and_get_url,
)

from google_client import get_drive_service

import requests
from googleapiclient.discovery import Resource

# from domain.models import DeliveryOrder

logger = logging.getLogger(__name__)

def save_barcode_to_folder(
        qr: str,
        *,
        drive: Resource,
        folder_id: str,
        base_url: str = "https://barcodeapi.org/api/128",
        timeout_seconds: int = 10,
        max_download_retries: int = 3,
) -> Optional[BarcodeResult]:
    if not qr or not isinstance(qr, str):
        raise ValueError("qr must be a non-empty string")

    image_name = f"{qr}.jpg"
    image_url = f"{base_url}/{qr}?"

    # 1️⃣ Check if already exists
    existing = find_file_in_folder_by_name(drive, folder_id, image_name)
    if existing:
        file_id = existing["id"]
        public_url = ensure_file_public_and_get_url(drive, file_id)

        logger.info('Barcode "%s" already exists (fileId=%s)', image_name, file_id)

        return BarcodeResult(
            file_id=file_id,
            public_url=public_url,
        )

    logger.info('Barcode "%s" not found, downloading...', image_name)

    # 2️⃣ Download with retry
    last_error = None
    content = None

    for attempt in range(1, max_download_retries + 1):
        try:
            resp = requests.get(image_url, timeout=timeout_seconds)
            resp.raise_for_status()
            content = resp.content
            break
        except Exception as e:
            last_error = e
            logger.warning(
                "Download failed (%d/%d): %s",
                attempt,
                max_download_retries,
                e,
            )

    if content is None:
        logger.error("Giving up downloading barcode for %s: %s", qr, last_error)
        return None

    # 3️⃣ Upload to Drive
    file_id = upload_file_to_folder(
        drive=drive,
        folder_id=folder_id,
        filename=image_name,
        mimetype="image/jpeg",
        media_stream=io.BytesIO(content),
    )

    public_url = ensure_file_public_and_get_url(drive, file_id)

    logger.info('Uploaded barcode "%s" as fileId=%s', image_name, file_id)

    return BarcodeResult(
        file_id=file_id,
        public_url=public_url,
    )


def get_barcode_url_list(
        delivery_order: DeliveryOrder,
        drive: Resource,
) -> list[BarcodeResult]:
    load_dotenv()
    barcode_url = []
    for item in delivery_order.lines:
        barcode_result = save_barcode_to_folder(
            item.sku,
            drive=drive,
            folder_id=os.getenv("BARCODE_FOLDER_ID"),
        )
        barcode_url.append(barcode_result)
    return barcode_url
