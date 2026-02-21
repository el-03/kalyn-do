import os
from typing import Dict, List, Any, Tuple, Optional
from dotenv import load_dotenv
from supabase import create_client, Client
from datetime import datetime, timezone

load_dotenv()
url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")
schema: str = os.getenv("SCHEMA")

supabase: Client = create_client(url, key)


def is_exist(table_name: str, col_name, val) -> bool:
    response = (
        supabase.schema(schema)
        .table(table_name)
        .select("*")
        .ilike(col_name, val)
        .execute()
    )
    return len(response.data) != 0


def insert_row(table_name: str, row: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Insert a single row (form-style).
    Returns (ok, message, inserted_row)
    """
    try:
        resp = (
            supabase.schema(schema)
            .table(table_name)
            .insert(row)
            .execute()
        )

        if getattr(resp, "error", None):
            return False, f"Insert failed: {resp.error}", None

        inserted = resp.data[0] if resp.data else None
        return True, "Inserted", inserted

    except Exception as e:
        return False, str(e), None


def fetch_column(
        table_name: str,
        col_name: str,
        as_tuple: bool = False,
) -> Tuple[bool, str, List[Any] | Tuple[Any, ...]]:
    """
    Fetch all values from a specific column.
    Returns (ok, message, values)
    """

    try:
        resp = (
            supabase.schema(schema)
            .table(table_name)
            .select(col_name)
            .execute()
        )

        if getattr(resp, "error", None):
            return False, f"Fetch failed: {resp.error}", []

        if not resp.data:
            return True, "No rows found", ()

        values = [row[col_name] for row in resp.data]

        if as_tuple:
            return True, "Fetched", tuple(values)

        return True, "Fetched", values

    except Exception as e:
        return False, f"Unexpected error: {e}", []


def fetch_column_w_id(
        table_name: str,
        col_name: str,
) -> Tuple[bool, str, dict]:
    """
    Returns (ok, message, {value: id})
    """

    try:
        resp = (
            supabase.schema(schema)
            .table(table_name)
            .select(f"id, {col_name}")
            .execute()
        )

        if getattr(resp, "error", None):
            return False, f"Fetch failed: {resp.error}", {}

        if not resp.data:
            return True, "No rows found", {}

        value_id_map = {row[col_name]: row["id"] for row in resp.data}

        return True, "Fetched", value_id_map

    except Exception as e:
        return False, f"Unexpected error: {e}", {}


def get_id_by_value(table: str, column: str, value: Any) -> Optional[int]:
    resp = (
        supabase.schema(schema)
        .table(table)
        .select("id")
        .eq(column, value)
        .limit(1)
        .execute()
    )
    if getattr(resp, "error", None):
        raise Exception(resp.error)

    if resp.data:
        return resp.data[0]["id"]
    return None


def insert_item(row: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Ensure an item exists and set/update its price.

    row must contain:
      - category_id
      - item_name_id
      - color_id
      - harga_kain
      - ongkos_jahit
      - ongkos_transport
      - ongkos_packing
      - optional: created_year

    Behaviour:
      - If item (category_id, item_name_id, color_id) does NOT exist:
          -> create item
          -> insert initial price in item_price_history
      - If item already exists:
          -> re-use it
          -> if price changed: close old price (valid_to) and insert new version
          -> if price same: do nothing to price
    """
    try:
        # --------------------------------------------------------
        # 1) Find or create the item
        # --------------------------------------------------------
        item_lookup = (
            supabase.schema(schema)
            .table("item")
            .select("*")
            .eq("category_id", row["category_id"])
            .eq("item_name_id", row["item_name_id"])
            .eq("color_id", row["color_id"])
            .limit(1)
            .execute()
        )

        if getattr(item_lookup, "error", None):
            return False, f"Item lookup failed: {item_lookup.error}", None

        if item_lookup.data:
            # Item exists, reuse it
            item_row = item_lookup.data[0]
            item_id = item_row["id"]
            item_is_new = False
        else:
            # Create new item
            item_payload = {
                "category_id": row["category_id"],
                "item_name_id": row["item_name_id"],
                "color_id": row["color_id"],
            }
            if "created_year" in row and row["created_year"] is not None:
                item_payload["created_year"] = row["created_year"]

            item_insert = (
                supabase.schema(schema)
                .table("item")
                .insert(item_payload)
                .execute()
            )

            if getattr(item_insert, "error", None):
                return False, f"Insert item failed: {item_insert.error}", None

            if not item_insert.data:
                return False, "Insert item failed: no data returned", None

            item_row = item_insert.data[0]
            item_id = item_row["id"]
            item_is_new = True

        # --------------------------------------------------------
        # 2) Handle pricing via item_price_history
        # --------------------------------------------------------
        new_price = {
            "harga_kain": row["harga_kain"],
            "ongkos_jahit": row["ongkos_jahit"],
            "ongkos_transport": row["ongkos_transport"],
            "ongkos_packing": row["ongkos_packing"],
        }

        current_price_resp = (
            supabase.schema(schema)
            .table("item_price_current")
            .select("id, harga_kain, ongkos_jahit, ongkos_transport, ongkos_packing")
            .eq("item_id", item_id)
            .limit(1)
            .execute()
        )

        if getattr(current_price_resp, "error", None):
            return False, f"Price lookup failed: {current_price_resp.error}", {"item": item_row}

        price_changed = False
        price_row: Optional[Dict[str, Any]] = None

        if not current_price_resp.data:
            # No price yet: insert initial price
            price_insert_payload = {"item_id": item_id, **new_price}
            price_insert = (
                supabase.schema(schema)
                .table("item_price_history")
                .insert(price_insert_payload)
                .execute()
            )

            if getattr(price_insert, "error", None):
                return False, f"Insert price failed: {price_insert.error}", {"item": item_row}

            price_row = price_insert.data[0] if price_insert.data else None
            price_changed = True
        else:
            current = current_price_resp.data[0]

            same_price = all(
                current[k] == new_price[k]
                for k in ("harga_kain", "ongkos_jahit", "ongkos_transport", "ongkos_packing")
            )

            if same_price:
                # Price unchanged, just reuse current price row
                price_row = current
                price_changed = False
            else:
                # Close old version
                now_iso = datetime.now(timezone.utc).isoformat()

                price_close = (
                    supabase.schema(schema)
                    .table("item_price_history")
                    .update({"valid_to": now_iso})
                    .eq("id", current["id"])
                    .execute()
                )

                if getattr(price_close, "error", None):
                    return False, f"Closing old price failed: {price_close.error}", {"item": item_row}

                # Insert new version
                price_insert_payload = {"item_id": item_id, **new_price}
                price_insert = (
                    supabase.schema(schema)
                    .table("item_price_history")
                    .insert(price_insert_payload)
                    .execute()
                )

                if getattr(price_insert, "error", None):
                    return False, f"Insert new price failed: {price_insert.error}", {"item": item_row}

                price_row = price_insert.data[0] if price_insert.data else None
                price_changed = True

        # --------------------------------------------------------
        # 3) Build a nice message
        # --------------------------------------------------------
        if item_is_new and price_changed:
            msg = "Item baru dibuat dan harga diset."
        elif not item_is_new and price_changed:
            msg = "Item sudah ada, harga diperbarui."
        elif not item_is_new and not price_changed:
            msg = "Item sudah ada, harga tetap sama."
        else:
            # theoretically: new item but no price change (won't really happen)
            msg = "Item baru dibuat."

        return True, msg, {
            "item": item_row,
            "price": price_row,
            "price_changed": price_changed,
        }

    except Exception as e:
        return False, str(e), None


def insert_stock_log(row: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Insert a stock movement row.

    You can pass either:
      A) item_id directly
         - item_id
         - store_id
         - jumlah_barang
         - movement_type
         - optional: size

      B) or the combination of IDs to resolve the item:
         - category_id
         - item_name_id
         - color_id
         - store_id
         - jumlah_barang
         - movement_type
         - optional: size
    """

    try:
        movement_type = row["movement_type"]

        if movement_type not in (
                "in_stock",
                "out",
                "adjustment",
                "transfer_in",
                "transfer_out",
        ):
            return False, f"Invalid movement_type: {movement_type}", None

        qty = row.get("jumlah_barang")
        if qty is None:
            return False, "Missing jumlah_barang", None

        if qty == 0:
            return False, "Quantity cannot be zero", None

        # Enforce sign rules
        if movement_type in ("out", "transfer_out"):
            qty = -abs(qty)
        elif movement_type in ("in_stock", "transfer_in"):
            qty = abs(qty)
        # adjustment: allow as is (positive or negative)

        # Resolve item_id
        item_id = row.get("item_id")

        if item_id is None:
            # Fall back to lookup by category_id + item_name_id + color_id
            for key in ("category_id", "item_name_id", "color_id"):
                if key not in row:
                    return False, f"Missing {key} to resolve item_id", None

            item_lookup_resp = (
                supabase.schema(schema)
                .table("item")
                .select("id")
                .eq("category_id", row["category_id"])
                .eq("item_name_id", row["item_name_id"])
                .eq("color_id", row["color_id"])
                .execute()
            )

            if getattr(item_lookup_resp, "error", None):
                return False, f"Item lookup failed: {item_lookup_resp.error}", None

            if not item_lookup_resp.data:
                return False, (
                    "Item not found for given category_id/item_name_id/color_id"
                ), None

            # ux_item_unique guarantees max 1
            item_id = item_lookup_resp.data[0]["id"]

        payload = {
            "item_id": item_id,
            "store_id": row["store_id"],
            "size": row.get("size", "OS"),
            "movement_type": movement_type,
            "quantity": qty,
        }

        resp = (
            supabase.schema(schema)
            .table("item_stock_log")
            .insert(payload)
            .execute()
        )

        if getattr(resp, "error", None):
            return False, f"Insert stock log failed: {resp.error}", None

        inserted = resp.data[0] if resp.data else None
        return True, "Inserted stock log", inserted

    except Exception as e:
        return False, str(e), None


def get_item_cost(category_id: int, item_name_id: int, color_id: int) -> Optional[Dict[str, Any]]:
    """
    Get the current cost components for a given (category, item_name, color).

    Uses:
      - item table to resolve item_id
      - item_price_current view to get the active price row

    Returns a dict with:
      { "harga_kain": ..., "ongkos_jahit": ..., "ongkos_transport": ..., "ongkos_packing": ... }
    or None if the item or its price is not found.
    """

    # 1) Resolve item_id from the master item table
    item_resp = (
        supabase.schema(schema)
        .table("item")
        .select("id")
        .eq("category_id", category_id)
        .eq("item_name_id", item_name_id)
        .eq("color_id", color_id)
        .limit(1)
        .execute()
    )

    if getattr(item_resp, "error", None):
        raise Exception(f"Item lookup failed: {item_resp.error}")

    if not item_resp.data:
        # No such item
        return None

    item_id = item_resp.data[0]["id"]

    # 2) Get the current price for this item from the view
    price_resp = (
        supabase.schema(schema)
        .table("item_price_current")
        .select("harga_kain, ongkos_jahit, ongkos_transport, ongkos_packing")
        .eq("item_id", item_id)
        .limit(1)
        .execute()
    )

    if getattr(price_resp, "error", None):
        raise Exception(f"Price lookup failed: {price_resp.error}")

    if not price_resp.data:
        # Item exists, but no current price set yet
        return None

    return price_resp.data[0]


def transfer_stock(
        item_name_id: int,
        category_id: int,
        color_id: int,
        size: str,
        from_store_id: int,
        to_store_id: int,
        quantity: int,
) -> tuple[bool, str]:
    """
    Transfer stock between stores using DB function.

    Moves `quantity` units from from_store_id to to_store_id
    in a single transaction on the database.
    """
    try:
        if quantity <= 0:
            return False, "Quantity must be positive"

        resp = (
            supabase
            .rpc(
                "transfer_stock",  # function name in Postgres
                {
                    "p_item_name_id": item_name_id,
                    "p_category_id": category_id,
                    "p_color_id": color_id,
                    "p_size": size,
                    "p_from_store_id": from_store_id,
                    "p_to_store_id": to_store_id,
                    "p_quantity": quantity,
                },
            )
            .execute()
        )

        if getattr(resp, "error", None):
            return False, f"Transfer failed: {resp.error}"

        return True, "Transfer OK"

    except Exception as e:
        return False, str(e)


def get_item_qty_stock(
    category_id: int,
    item_name_id: int,
    color_id: int,
    store_id: int,
    size: Optional[str] = "OS",
) -> Tuple[bool, str, int]:
    """
    Get current stock quantity for a specific item + store.

    Returns:
        (ok, message, quantity)
    """

    try:
        # 1) Resolve the item_id from the master table
        item_resp = (
            supabase.schema(schema)
            .table("item")
            .select("id")
            .eq("category_id", category_id)
            .eq("item_name_id", item_name_id)
            .eq("color_id", color_id)
            .limit(1)
            .execute()
        )

        if getattr(item_resp, "error", None):
            return False, f"Fetch item failed: {item_resp.error}", 0

        if not item_resp.data:
            # No such item defined in master data
            return True, "Item not found", 0

        item_id = item_resp.data[0]["id"]

        # 2) Read stock snapshot for that item_id + store + size
        stock_resp = (
            supabase.schema(schema)
            .table("item_stock")
            .select("quantity")
            .eq("item_id", item_id)
            .eq("store_id", store_id)
            .eq("size", size)
            .limit(1)
            .execute()
        )

        if getattr(stock_resp, "error", None):
            return False, f"Fetch stock failed: {stock_resp.error}", 0

        if not stock_resp.data:
            # Item exists, but no stock row yet → treat as 0
            return True, "No stock found", 0

        quantity = stock_resp.data[0]["quantity"]
        return True, "Fetched", quantity

    except Exception as e:
        return False, str(e), 0

def get_items_in_stock(store_id: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
    """
    Returns a dict of items currently in stock.

    Structure (one entry per SKU+size):
    {
        "<sku>|<size>": {
            "item_name": str,
            "category": str,
            "color": str,
            "sku": str,
            "size": str,
            "harga_jual": int | None,
            "quantity": int,

            # for transfer_stock(...)
            "item_name_id": int,
            "category_id": int,
            "color_id": int,
        },
        ...
    }

    If store_id is provided, filters by that store.
    """
    try:
        # 1) Get stock + item metadata (no price here)
        stock_query = (
            supabase.schema(schema)
            .table("item_stock")
            .select(
                """
                quantity,
                size,
                item:item_id (
                    id,
                    sku,
                    item_name_id,
                    category_id,
                    color_id,
                    item_name:item_name_id ( item_name ),
                    category:category_id ( category ),
                    color:color_id ( color )
                )
                """
            )
            .gt("quantity", 0)
        )

        if store_id is not None:
            stock_query = stock_query.eq("store_id", store_id)

        stock_resp = stock_query.execute()

        if getattr(stock_resp, "error", None):
            raise Exception(stock_resp.error)

        if not stock_resp.data:
            return {}

        # 2) Collect all item_ids from the first query
        item_ids = {
            row["item"]["id"]
            for row in stock_resp.data
            if row.get("item") and row["item"].get("id") is not None
        }

        if not item_ids:
            return {}

        # 3) Fetch current prices for those items from the view
        price_resp = (
            supabase.schema(schema)
            .table("item_price_current")
            .select("item_id,harga_jual")
            .in_("item_id", list(item_ids))
            .execute()
        )

        if getattr(price_resp, "error", None):
            raise Exception(price_resp.error)

        prices_by_item_id: Dict[int, Any] = {
            row["item_id"]: row["harga_jual"] for row in (price_resp.data or [])
        }

        # 4) Build the result grouped by SKU + size
        result: Dict[str, Dict[str, Any]] = {}

        for row in stock_resp.data:
            item = row.get("item")
            if not item:
                continue

            item_id = item["id"]
            sku = item["sku"]
            size = row.get("size", "OS")

            item_name_obj = item.get("item_name") or {}
            category_obj = item.get("category") or {}
            color_obj = item.get("color") or {}

            item_name = item_name_obj.get("item_name")
            category = category_obj.get("category")
            color = color_obj.get("color")

            harga_jual = prices_by_item_id.get(item_id)

            item_name_id = item.get("item_name_id")
            category_id = item.get("category_id")
            color_id = item.get("color_id")

            # key is SKU + size so we don't mix sizes
            key = f"{sku}|{size}"

            if key not in result:
                result[key] = {
                    "item_name": item_name,
                    "category": category,
                    "color": color,
                    "sku": sku,
                    "size": size,
                    "harga_jual": harga_jual,
                    "quantity": 0,
                    "item_name_id": item_name_id,
                    "category_id": category_id,
                    "color_id": color_id,
                }

            # Sum quantity across rows with same SKU+size
            result[key]["quantity"] += row["quantity"]

        return result

    except Exception as e:
        raise Exception(f"Failed to get items in stock: {e}") from e


def transfer_via_logs(
    *,
    item_id: int,
    size: str,
    from_store_id: int,
    to_store_id: int,
    quantity: int,
) -> tuple[bool, str]:
    """
    Transfer stock by writing two item_stock_log rows:
      - transfer_out from from_store_id
      - transfer_in  to   to_store_id

    Quantity is positive here; insert_stock_log will handle the sign.
    """
    if quantity <= 0:
        return False, "Quantity must be positive"

    # 1) transfer_out from source
    ok_out, msg_out, _ = insert_stock_log(
        {
            "item_id": item_id,
            "store_id": from_store_id,
            "jumlah_barang": quantity,
            "movement_type": "transfer_out",
            "size": size,
        }
    )
    if not ok_out:
        return False, f"transfer_out failed: {msg_out}"

    # 2) transfer_in to destination
    ok_in, msg_in, _ = insert_stock_log(
        {
            "item_id": item_id,
            "store_id": to_store_id,
            "jumlah_barang": quantity,
            "movement_type": "transfer_in",
            "size": size,
        }
    )
    if not ok_in:
        # at this point gudang has already been reduced;
        # you *could* add a compensating transfer_in back to gudang if you want.
        return False, f"transfer_in failed after transfer_out: {msg_in}"

    return True, "Transfer OK"

def get_item_id_from_attrs(category_id: int, item_name_id: int, color_id: int):
    """
    Resolve item_id from category/item_name/color.
    Returns (ok, msg, item_id_or_none)
    """
    try:
        resp = (
            supabase.schema(schema)
            .table("item")
            .select("id")
            .eq("category_id", category_id)
            .eq("item_name_id", item_name_id)
            .eq("color_id", color_id)
            .limit(1)
            .execute()
        )

        if getattr(resp, "error", None):
            return False, f"Fetch item_id failed: {resp.error}", None

        if not resp.data:
            return False, "Item belum terdaftar di master item", None

        return True, "OK", resp.data[0]["id"]
    except Exception as e:
        return False, str(e), None


def get_item_qty_stock_by_item_id(
    item_id: int,
    store_id: int,
    size: str = "OS",
):
    """
    Returns: (ok, msg, quantity)
    """
    try:
        resp = (
            supabase.schema(schema)
            .table("item_stock")
            .select("quantity")
            .eq("item_id", item_id)
            .eq("store_id", store_id)
            .eq("size", size)
            .limit(1)
            .execute()
        )

        if getattr(resp, "error", None):
            return False, f"Fetch stock failed: {resp.error}", 0

        if not resp.data:
            return True, "No stock found", 0

        return True, "Fetched", resp.data[0]["quantity"]
    except Exception as e:
        return False, str(e), 0

def get_item_qty_stock_by_item_id(
    item_id: int,
    store_id: int,
    size: str = "OS",
) -> Tuple[bool, str, int]:
    try:
        resp = (
            supabase.schema(schema)
            .table("item_stock")
            .select("quantity")
            .eq("item_id", item_id)
            .eq("store_id", store_id)
            .eq("size", size)
            .limit(1)
            .execute()
        )

        if getattr(resp, "error", None):
            return False, f"Fetch stock failed: {resp.error}", 0

        if not resp.data:
            return True, "No stock found", 0

        qty = resp.data[0]["quantity"]
        return True, "Fetched", qty

    except Exception as e:
        return False, str(e), 0