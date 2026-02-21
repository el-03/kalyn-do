import streamlit as st
import pandas as pd
from data_integrator import (
    fetch_column_w_id,
    insert_stock_log,
    get_item_id_from_attrs,          # NEW
    get_item_qty_stock_by_item_id,   # NEW
)

st.set_page_config(
    page_title="Update Stock Barang",
    page_icon="👗"
)

st.sidebar.header("👗 Update Stock Barang")


@st.dialog("Konfirmasi")
def confirmation_dialog(value, state_name):
    df = pd.DataFrame(list(value.items()), columns=["Key", "Value"])
    df["Value"] = df["Value"].astype("string")
    st.dataframe(df, hide_index=True)

    if st.button("Ya"):
        ins_status, ins_msg, ins_val = insert_stock_log(value)
        if ins_status:
            st.session_state[state_name] = True
            st.rerun()
        else:
            st.error(ins_msg)
    if st.button("Tidak"):
        st.rerun()


# -------------------------------------------------------------------
# Session state defaults
# -------------------------------------------------------------------

if "stock_update_state" not in st.session_state:
    st.session_state["stock_update_state"] = False
    st.session_state["get_item_stock"] = False
    st.session_state["valid_item_detail"] = False
    st.session_state["item_stock_val"] = None

defaults = {
    "category": None,
    "item_name": None,
    "color": None,
    "category_id": None,
    "item_name_id": None,
    "color_id": None,
    "item_id": None,          # NEW
    "size": "OS",
    "jumlah_barang": 0,
}

for k, v in defaults.items():
    st.session_state.setdefault(k, v)

# -------------------------------------------------------------------
# Dropdowns
# -------------------------------------------------------------------

st.subheader("Update Stock Barang")
ok_1, msg_1, category_map = fetch_column_w_id("category", "category")
ok_2, msg_2, item_name_map = fetch_column_w_id("item_name", "item_name")
ok_3, msg_3, color_map = fetch_column_w_id("color", "color")

if ok_1 and category_map.keys():
    cat_val = st.selectbox(
        "Kategori",
        category_map.keys(),
        index=None,
        placeholder="Pilih Kategori",
        key="category",
    )
else:
    st.error("Could not load category")

if ok_2 and item_name_map.keys():
    item_name_val = st.selectbox(
        "Nama Barang",
        item_name_map.keys(),
        index=None,
        placeholder="Pilih Nama Barang",
        key="item_name",
    )
else:
    st.error("Could not load item_name")

if ok_3 and color_map.keys():
    color_val = st.selectbox(
        "Warna",
        color_map.keys(),
        index=None,
        placeholder="Pilih Warna",
        key="color",
    )
else:
    st.error("Could not load color")

st.selectbox(
    "Ukuran",
    ("OS", "XS", "S", "M", "L", "XL", "XXL"),
    key="size",
)

# -------------------------------------------------------------------
# Cek stok di gudang (resolve item_id + get stock)
# -------------------------------------------------------------------

GUDANG_STORE_ID = 4  # 'gudang' dari seed

if st.button("Cek Jumlah Barang di Gudang"):
    st.session_state["stock_update_state"] = False

    item_detail = {
        "category": st.session_state["category"],
        "item_name": st.session_state["item_name"],
        "color": st.session_state["color"],
        "size": st.session_state["size"],
    }

    required_fields = ["category", "item_name", "color", "size"]
    missing = [k for k in required_fields if item_detail[k] is None]

    if missing:
        st.error(f"Semua input harus diisi! Field kosong: {', '.join(missing)}")
    else:
        # Map label → id
        st.session_state["category_id"] = category_map[item_detail["category"]]
        st.session_state["item_name_id"] = item_name_map[item_detail["item_name"]]
        st.session_state["color_id"] = color_map[item_detail["color"]]

        # 1) Resolve item_id dari kombinasi tersebut
        ok_item, msg_item, item_id = get_item_id_from_attrs(
            st.session_state["category_id"],
            st.session_state["item_name_id"],
            st.session_state["color_id"],
        )

        if not ok_item or item_id is None:
            st.session_state["valid_item_detail"] = False
            st.session_state["item_stock_val"] = None
            st.error(msg_item)
        else:
            st.session_state["item_id"] = item_id

            # 2) Ambil stok berdasarkan item_id
            st.session_state["item_stock_val"] = get_item_qty_stock_by_item_id(
                item_id,
                GUDANG_STORE_ID,
                st.session_state["size"],
            )
            st.session_state["valid_item_detail"] = True

# -------------------------------------------------------------------
# Form update stock
# -------------------------------------------------------------------

with st.form("update_stock_input_form"):
    current_stock = 0
    qty = st.session_state["jumlah_barang"]

    st.number_input("Jumlah Barang", step=1, key="jumlah_barang")

    if st.session_state["item_stock_val"]:
        current_stock = st.session_state["item_stock_val"][2]
        st.caption(f"Jumlah Barang di Gudang: **{current_stock}**")

    if st.form_submit_button("Submit"):

        # Payload sekarang pakai item_id, bukan triple ID
        payload = {
            "item_id": st.session_state["item_id"],
            "store_id": GUDANG_STORE_ID,
            "movement_type": "adjustment" if qty < 0 else "in_stock",
            "size": st.session_state["size"],
            "jumlah_barang": qty,
        }

        if not st.session_state["valid_item_detail"] or st.session_state["item_id"] is None:
            st.error("Mohon cek jumlah barang di gudang terlebih dahulu")
        else:
            if qty == 0:
                st.error("Jumlah barang tidak boleh 0")
            elif current_stock + qty < 0:
                st.error("Melebihi batas stok yang ada")
            else:
                confirmation_dialog(payload, "stock_update_state")

    if st.session_state["stock_update_state"]:
        st.success(f"Berhasil meng-update jumlah barang menjadi: {current_stock + qty}")