import csv
import os
from typing import Dict, List, Iterable, Optional

from dotenv import load_dotenv
from supabase import create_client, Client


BATCH_SIZE = 500


def chunked(items: List[Dict], size: int) -> Iterable[List[Dict]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def read_csv(file_name: str) -> tuple[List[Dict], List[str]]:
    """
    Reads a headered CSV and returns (rows, columns_from_header).
    Strips whitespace from headers and values.
    """
    with open(file_name, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row. Add headers that match DB column names.")

        columns = [c.strip() for c in reader.fieldnames if c and c.strip()]
        rows: List[Dict] = []

        for line_no, r in enumerate(reader, start=2):
            obj = {}
            for k, v in r.items():
                if not k:
                    continue
                key = k.strip()
                val = v.strip() if isinstance(v, str) else v
                # turn empty string into None so DB can handle NULLs
                if isinstance(val, str) and val == "":
                    val = None
                obj[key] = val

            # keep only the columns we saw in the header
            obj = {c: obj.get(c) for c in columns}
            rows.append(obj)

    return rows, columns


def dedupe_rows(rows: List[Dict], key_cols: List[str]) -> List[Dict]:
    """
    Deduplicate rows in-memory using key_cols.
    Keeps first occurrence.
    """
    seen = set()
    out: List[Dict] = []

    for r in rows:
        key = tuple((r.get(c) or "").strip() if isinstance(r.get(c), str) else (r.get(c) or "") for c in key_cols)
        # skip rows missing any key value
        if any(k == "" for k in key):
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(r)

    return out


def load_to_supabase(
    supabase: Client,
    schema_name: str,
    table_name: str,
    file_name: str,
    conflict_cols: List[str],
    column_list: Optional[List[str]] = None,
    batch_size: int = BATCH_SIZE,
) -> None:
    rows, header_cols = read_csv(file_name)

    # If you didn't pass column_list, use the CSV header
    if column_list is None:
        column_list = header_cols

    # Safety check: ensure requested columns exist in CSV
    missing = [c for c in column_list if c not in header_cols]
    if missing:
        raise ValueError(f"CSV missing columns: {missing}. Found: {header_cols}")

    # Allow only those columns to go to DB
    filtered = [{c: r.get(c) for c in column_list} for r in rows]

    # Dedupe before pushing (based on conflict columns)
    deduped = dedupe_rows(filtered, conflict_cols)

    if not deduped:
        print("No valid rows to insert (after dedupe / missing key filtering).")
        return

    total = 0
    for batch in chunked(deduped, batch_size):
        supabase.schema(schema_name).table(table_name).upsert(
            batch,
            on_conflict=",".join(conflict_cols)
        ).execute()
        total += len(batch)
        print(f"Upserted {len(batch)} rows (running total: {total})")

    print(f"Done: {schema_name}.{table_name} <- {file_name} ({total} unique rows)")


if __name__ == "__main__":
    load_dotenv()

    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")  # use SERVICE_ROLE for scripts
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Set SUPABASE_URL and SUPABASE_KEY in .env or environment variables")

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # ======= VARIABLES YOU CHANGE =======
    schema_name = "kalyn_db_test"
    # table_name = "category"
    # file_name = "../raw_data/category.csv"
    # conflict_cols = ["category"]
    # table_name = "color"
    # file_name = "../raw_data/color.csv"
    # conflict_cols = ["color"]
    table_name = "item_name"
    file_name = "../raw_data/item_name.csv"
    conflict_cols = ["item_name"]

    # tables = ["category", "color", "item_name"]
    # files = ["../raw_data/category.csv", "../raw_data/color.csv", "../raw_data/item_name.csv"]
    # conflict_cols = ["category", "color", "item_name"]

    # This must match a UNIQUE constraint in Postgres for true “no duplicates”

    # If you want: column_list = None (auto from CSV header)
    column_list = None
    # ====================================

    load_to_supabase(
        supabase=supabase,
        schema_name=schema_name,
        table_name=table_name,
        file_name=file_name,
        conflict_cols=conflict_cols,
        column_list=column_list,
    )
