import streamlit as st
import pandas as pd
from data_integrator import get_items_in_stock

st.set_page_config(page_title="Delivery Order", page_icon="📦")

st.title("📦 Delivery Order Generator")

# --- Product catalog with fixed metadata ---
# Replace these with your real fields
items_in_stock = get_items_in_stock(4)
df = pd.DataFrame.from_dict(items_in_stock, orient="index").reset_index(drop=True)
st.dataframe(df)

item_options = list(items_in_stock.keys())

# --- Session state: how many item rows? ---
if "num_items" not in st.session_state:
    st.session_state.num_items = 1  # start with one row

# Button to add more item rows (outside the form)
if st.button("➕ Tambah Item"):
    st.session_state.num_items += 1

st.write(f"Jumlah Item: {st.session_state.num_items}")

# --- The form for the whole order ---
with st.form("delivery_order_form"):
    st.subheader("Items")

    # Render dynamic item rows
    for i in range(st.session_state.num_items):
        st.markdown(f"**Item {i + 1}**")

        col1, col2 = st.columns([2, 1])
        with col1:
            item = st.selectbox(
                "Item",
                options=item_options,
                key=f"item_{i}",
            )
        with col2:
            qty = st.number_input(
                "Jumlah",
                min_value=1,
                step=1,
                value=1,
                key=f"qty_{i}",
            )

        # Lookup metadata for the selected item
        meta = items_in_stock.get(item, {})
        item = meta.get("item_name")
        harga_jual = meta.get("harga_jual", 0.0)
        formatted_harga = f"Rp {harga_jual:,.0f}".replace(",", ".")
        sku = meta.get("sku", "")
        max_qty = meta.get("quantity", "")
        category = meta.get("category", "")

        # Read-only reference info (visible but not editable)
        # You can change layout here however you like
        st.caption(
            f"Item: **{item}** | Cat: **{category}** | SKU: **{sku}** | Max. Qty: **{max_qty}** | Harga Jual: **{formatted_harga}**"
        )

        st.divider()

    submitted = st.form_submit_button("Generate Delivery Order")

# --- After submit: build full order + compute totals ---
if submitted:
    order_rows = []

    for i in range(st.session_state.num_items):
        item = st.session_state.get(f"item_{i}")
        qty = st.session_state.get(f"qty_{i}", 0)

        if not item:
            continue

        meta = items_in_stock[item]
        unit_price = meta["unit_price"]
        total = unit_price * qty

        order_rows.append(
            {
                "Item": item,
                "Quantity": qty,
                "Unit Price": unit_price,
                "SKU": meta["sku"],
                "Unit": meta["unit"],
                "Category": meta["category"],
                "Total": total,
            }
        )

    if not order_rows:
        st.error("No valid items in the order.")
    else:
        df = pd.DataFrame(order_rows)
        grand_total = df["Total"].sum()

        st.success("Delivery order generated ✅")

        st.subheader("Order Summary")
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.metric("Grand Total", f"{grand_total:,.2f}")

        # Optional: download as CSV
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download as CSV",
            data=csv,
            file_name="delivery_order.csv",
            mime="text/csv",
        )
