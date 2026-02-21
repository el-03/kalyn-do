import streamlit as st
import pandas as pd

from data_integrator import get_items_in_stock, transfer_via_logs

# -----------------------------------------------------------------------------
# Page config
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Delivery Order", page_icon="📦")
st.title("📦 Delivery Order Generator")

# -----------------------------------------------------------------------------
# Store configuration
# -----------------------------------------------------------------------------
STORE_ID_BY_NAME = {
    "banda": 1,
    "karawang": 2,
    "purwakarta": 3,
    "gudang": 4,
}

WAREHOUSE_STORE_NAME = "gudang"
WAREHOUSE_STORE_ID = STORE_ID_BY_NAME[WAREHOUSE_STORE_NAME]

# -----------------------------------------------------------------------------
# 1) Pick destination store
# -----------------------------------------------------------------------------
store_name = st.selectbox(
    "Store tujuan",
    options=[name for name in STORE_ID_BY_NAME.keys() if name != WAREHOUSE_STORE_NAME],
)
target_store_id = STORE_ID_BY_NAME[store_name]

st.write(f"Stok akan dikirim dari **{WAREHOUSE_STORE_NAME}** ke **{store_name}**.")
st.divider()

# -----------------------------------------------------------------------------
# 2) Load stock from gudang
# -----------------------------------------------------------------------------
items_in_stock = get_items_in_stock(WAREHOUSE_STORE_ID)
# Expected per key "<sku>|<size>":
# {
#   "item_name": str,
#   "category": str,
#   "color": str,
#   "sku": str,
#   "size": str,
#   "harga_jual": int | None,
#   "quantity": int,
#   "item_id": int,
# }

if not items_in_stock:
    st.warning("Tidak ada stok di gudang.")
    st.stop()

# Raw and display dataframes
df_stock_raw = pd.DataFrame.from_dict(items_in_stock, orient="index").reset_index(drop=True)

df_stock_display = df_stock_raw[
    ["item_name", "category", "color", "sku", "size", "harga_jual", "quantity"]
].copy()

df_stock_display = df_stock_display.rename(
    columns={
        "item_name": "Item",
        "category": "Kategori",
        "color": "Warna",
        "sku": "SKU",
        "size": "Size",
        "harga_jual": "Harga Jual",
        "quantity": "Qty",
    }
)

df_stock_display["Harga Jual"] = df_stock_display["Harga Jual"].apply(
    lambda x: f"Rp {x:,.0f}".replace(",", ".") if pd.notnull(x) else "-"
)

st.subheader("Stok Gudang")
st.dataframe(df_stock_display, width='stretch', hide_index=True)

# -----------------------------------------------------------------------------
# 3) Helper maps for SKU and Size
# -----------------------------------------------------------------------------
sku_set = set()
sku_size_to_key = {}

for key, meta in items_in_stock.items():
    sku = meta["sku"]
    size = meta["size"]
    sku_set.add(sku)
    sku_size_to_key[(sku, size)] = key

sku_options_all = sorted(sku_set)

st.divider()

# -----------------------------------------------------------------------------
# 4) Manage number of line items
# -----------------------------------------------------------------------------
if "num_items" not in st.session_state:
    st.session_state.num_items = 1


if st.button("➕ Tambah Item"):
    st.session_state.num_items += 1

st.subheader("Items yang akan dikirim")

# -----------------------------------------------------------------------------
# 5) Dynamic rows with UNIQUE (SKU, Size) rule
# -----------------------------------------------------------------------------
for i in range(st.session_state.num_items):
    st.markdown(f"**Item {i + 1}**")

    col_sku, col_size, col_qty = st.columns([2, 1.5, 1])

    # (1) Pairs (SKU, Size) already chosen in previous rows
    used_pairs_before = set()
    for j in range(i):
        prev_sku = st.session_state.get(f"sku_{j}")
        prev_size = st.session_state.get(f"size_{j}")
        if prev_sku and prev_size:
            used_pairs_before.add((prev_sku, prev_size))

    # (2) Determine which SKUs still have at least one free size
    current_selected_sku = st.session_state.get(f"sku_{i}")

    available_sku_options = []
    for sku in sku_options_all:
        # all sizes for this sku
        sizes_for_sku = {
            meta["size"]
            for meta in items_in_stock.values()
            if meta["sku"] == sku
        }
        # sizes not yet used for this sku
        remaining_sizes = [
            s for s in sizes_for_sku
            if (sku, s) not in used_pairs_before
        ]

        # keep SKU if it still has free sizes,
        # or if it's already selected in this row
        if remaining_sizes or sku == current_selected_sku:
            available_sku_options.append(sku)

    # If nothing is available, bail out for this row
    if not available_sku_options:
        st.info("Tidak ada kombinasi SKU+Size lain yang tersedia untuk dipilih.")
        st.divider()
        continue

    # (3) SKU dropdown with filtered options
    with col_sku:
        selected_sku = st.selectbox(
            "SKU",
            options=available_sku_options,
            key=f"sku_{i}",
        )

    # (4) Based on selected SKU, filter sizes that are not used yet
    sizes_for_selected_sku = sorted(
        {
            meta["size"]
            for meta in items_in_stock.values()
            if meta["sku"] == selected_sku
        }
    )

    current_selected_size = st.session_state.get(f"size_{i}")

    available_sizes = []
    for size in sizes_for_selected_sku:
        pair = (selected_sku, size)
        # allow if not used yet, or already selected in this row
        if pair not in used_pairs_before or size == current_selected_size:
            available_sizes.append(size)

    if not available_sizes:
        st.info(f"Tidak ada size tersisa untuk SKU {selected_sku}.")
        st.divider()
        continue

    with col_size:
        selected_size = st.selectbox(
            "Size",
            options=available_sizes,
            key=f"size_{i}",
        )

    # (5) Look up meta for this specific SKU+Size
    item_key = sku_size_to_key.get((selected_sku, selected_size))
    meta = items_in_stock.get(item_key, {}) if item_key else {}

    item_name = meta.get("item_name", "")
    harga_jual = meta.get("harga_jual", 0.0)
    max_qty = int(meta.get("quantity", 0) or 0)
    category = meta.get("category", "")
    color = meta.get("color", "")

    if max_qty < 1:
        max_qty = 1

    with col_qty:
        qty = st.number_input(
            "Jumlah",
            min_value=1,
            max_value=max_qty,
            step=1,
            value=1,
            key=f"qty_{i}",
        )

    formatted_harga = f"Rp {harga_jual:,.0f}".replace(",", ".")
    st.caption(
        f"Item: **{item_name}** | Kategori: **{category}** | Warna: **{color}** | "
        f"SKU: **{selected_sku}** | Size: **{selected_size}** | "
        f"Stok Gudang: **{meta.get('quantity', 0)}** | "
        f"Harga Jual: **{formatted_harga}**"
    )

    st.divider()

# -----------------------------------------------------------------------------
# 6) Submit: transfer via logs + summary
# -----------------------------------------------------------------------------
submitted = st.button("Transfer & Generate Delivery Order")

if submitted:
    order_rows = []
    transfer_results = []

    for i in range(st.session_state.num_items):
        selected_sku = st.session_state.get(f"sku_{i}")
        selected_size = st.session_state.get(f"size_{i}")
        qty = st.session_state.get(f"qty_{i}", 0)

        if not selected_sku or not selected_size or qty <= 0:
            continue

        item_key = sku_size_to_key.get((selected_sku, selected_size))
        if not item_key:
            continue

        meta = items_in_stock[item_key]

        item_id = meta["item_id"]
        size = meta["size"]
        sku = meta["sku"]

        harga_jual = meta.get("harga_jual", 0.0)
        item_name = meta.get("item_name", "")
        category = meta.get("category", "")
        color = meta.get("color", "")

        # Transfer via insert_stock_log (transfer_out + transfer_in)
        ok, msg = transfer_via_logs(
            item_id=item_id,
            size=size,
            from_store_id=WAREHOUSE_STORE_ID,
            to_store_id=target_store_id,
            quantity=qty,
        )
        transfer_results.append((sku, size, qty, ok, msg))

        total = harga_jual * qty

        order_rows.append(
            {
                "SKU": sku,
                "Size": size,
                "Item": item_name,
                "Category": category,
                "Color": color,
                "Quantity": qty,
                "Unit Price": harga_jual,
                "Total": total,
            }
        )

    if not order_rows:
        st.error("Tidak ada item yang valid.")
    else:
        st.subheader("Status Transfer")
        for sku, size, qty, ok, msg in transfer_results:
            if ok:
                st.success(f"Transfer {sku} ({size}) x{qty} ke {store_name}: {msg}")
            else:
                st.error(f"Transfer {sku} ({size}) x{qty} ke {store_name} gagal: {msg}")

        df_order = pd.DataFrame(order_rows)
        grand_total = df_order["Total"].sum()

        df_display = df_order.copy()
        df_display["Unit Price"] = df_display["Unit Price"].apply(
            lambda x: f"Rp {x:,.0f}".replace(",", ".")
        )
        df_display["Total"] = df_display["Total"].apply(
            lambda x: f"Rp {x:,.0f}".replace(",", ".")
        )

        st.subheader("Order Summary")
        st.dataframe(df_display, width='stretch', hide_index=True)

        st.metric("Grand Total", f"Rp {grand_total:,.0f}".replace(",", "."))

        csv = df_order.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download as CSV",
            data=csv,
            file_name="delivery_order.csv",
            mime="text/csv",
        )