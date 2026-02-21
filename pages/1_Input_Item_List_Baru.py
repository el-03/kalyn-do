import streamlit as st
import pandas as pd
from typing import Dict, Any
from data_integrator import insert_item, insert_stock_log,fetch_column_w_id, get_item_cost

st.set_page_config(page_title="Input Item List Baru", page_icon="👚")
st.sidebar.header("👚 Input Item List Baru")


@st.dialog("Konfirmasi")
def confirmation_dialog(value: Dict[str, Any], state_name: str):
    """
    Confirmation dialog before actually inserting.

    `value` should contain:
      - category_id, item_name_id, color_id
      - harga_kain, ongkos_jahit, ongkos_transport, ongkos_packing
      - jumlah_barang, size, store_id, movement_type
      - and optionally the display fields: category, item_name, color, store_name
    """

    # Build a user-friendly summary table
    display_rows = []

    labels = {
        "item_name": "Nama Barang",
        "category": "Kategori",
        "color": "Warna",
        "size": "Ukuran",
        "jumlah_barang": "Jumlah Barang",
        "harga_kain": "Harga Kain",
        "ongkos_jahit": "Ongkos Jahit",
        "ongkos_transport": "Ongkos Transport",
        "ongkos_packing": "Ongkos Packing",
        "store_name": "Toko",
        "movement_type": "Tipe Pergerakan",
    }

    display_order = [
        "item_name",
        "category",
        "color",
        "size",
        "jumlah_barang",
        "harga_kain",
        "ongkos_jahit",
        "ongkos_transport",
        "ongkos_packing",
        "store_name",
        "movement_type",
    ]

    for key in display_order:
        if key in value and value[key] is not None:
            display_rows.append(
                {"Field": labels.get(key, key), "Value": str(value[key])}
            )

    if display_rows:
        df = pd.DataFrame(display_rows)
        st.dataframe(df, hide_index=True, use_container_width=True)
    else:
        st.info("Tidak ada data untuk dikonfirmasi.")

    st.write("")

    col_yes, col_no = st.columns(2)

    with col_yes:
        if st.button("Ya", type="primary", key="confirm_yes"):
            # 1) Insert item + initial price
            ins_status_one, ins_msg_one, ins_val_one = insert_item(value)
            if not ins_status_one:
                st.error(f"Gagal insert item: {ins_msg_one}")
                return

            # Grab the new item_id from the result (if insert_item returns it in this shape)
            item_row = None
            if isinstance(ins_val_one, dict) and "item" in ins_val_one:
                item_row = ins_val_one["item"]
            else:
                # fallback: maybe ins_val_one is already the item row
                item_row = ins_val_one

            item_id = item_row.get("id") if item_row else None
            if item_id is None:
                st.error("Item berhasil dibuat, tapi item_id tidak ditemukan di respons.")
                return

            st.success("Item berhasil dibuat.")

            # 2) Insert stock log if jumlah_barang != 0
            if value.get("jumlah_barang", 0) != 0:
                value_with_item_id = {**value, "item_id": item_id}
                ins_status_two, ins_msg_two, ins_val_two = insert_stock_log(value_with_item_id)
                if not ins_status_two:
                    st.error(f"Gagal insert stock log: {ins_msg_two}")
                    # We still continue; item is created but stock log failed.
                else:
                    st.success("Stock log berhasil dibuat.")

            # mark handled and rerun
            st.session_state[state_name] = True
            st.rerun()

    with col_no:
        if st.button("Tidak", key="confirm_no"):
            st.session_state[state_name] = False
            st.rerun()


# Initialize defaults once
if 'item_list_input_state' not in st.session_state:
    st.session_state['item_list_input_state'] = False

defaults = {
    "category": None,
    "item_name": None,
    "color": None,
    "size": "OS",
    "jumlah_barang": 0,
    "harga_kain": 0,
    "ongkos_jahit": 0,
    "ongkos_transport": 0,
    "ongkos_packing": 0,
}

for k, v in defaults.items():
    st.session_state.setdefault(k, v)

st.subheader("Item List Input Form")

# Fetch master data
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

# Pre-fill ongkos from previous price if exists
if (
    st.button("Isi dengan Ongkos Sebelumnya")
    and st.session_state["category"]
    and st.session_state["item_name"]
    and st.session_state["color"]
):
    prev_costs = get_item_cost(
        category_map[st.session_state["category"]],
        item_name_map[st.session_state["item_name"]],
        color_map[st.session_state["color"]],
    )

    if prev_costs:
        for k, v in prev_costs.items():
            st.session_state[k] = v
        st.success("Ongkos lama ditemukan")
    else:
        st.warning("Tidak ditemukan ongkos sebelumnya")

    st.session_state['item_list_input_state'] = False

with st.form("item_list_input_form", enter_to_submit=False):
    st.selectbox(
        "Ukuran",
        ("OS", "XS", "S", "M", "L", "XL", "XXL"),
        key="size",
    )

    st.number_input("Jumlah Barang", min_value=0, step=1, key="jumlah_barang")

    st.number_input("Harga Kain", min_value=0, step=1, key="harga_kain")
    st.number_input("Ongkos Jahit", min_value=0, step=1, key="ongkos_jahit")
    st.number_input("Ongkos Transport", min_value=0, step=1, key="ongkos_transport")
    st.number_input("Ongkos Packing", min_value=0, step=1, key="ongkos_packing")

    submitted = st.form_submit_button("Submit")

    if submitted:
        if not (st.session_state["category"] and st.session_state["item_name"] and st.session_state["color"]):
            st.error("Semua input kategori / nama barang / warna harus diisi.")
        else:
            payload = {
                # DB IDs
                "category_id": category_map[st.session_state["category"]],
                "item_name_id": item_name_map[st.session_state["item_name"]],
                "color_id": color_map[st.session_state["color"]],

                # display fields for confirmation
                "category": st.session_state["category"],
                "item_name": st.session_state["item_name"],
                "color": st.session_state["color"],

                # store: hard-coded to 'gudang' (id=4) for now
                "store_id": 4,
                "store_name": "gudang",

                "movement_type": "in_stock",
                "size": st.session_state["size"],
                "jumlah_barang": st.session_state["jumlah_barang"],
                "harga_kain": st.session_state["harga_kain"],
                "ongkos_jahit": st.session_state["ongkos_jahit"],
                "ongkos_transport": st.session_state["ongkos_transport"],
                "ongkos_packing": st.session_state["ongkos_packing"],
            }

            # Validate only the fields that can be None
            required_fields = ["category_id", "item_name_id", "color_id", "size"]
            missing = [k for k in required_fields if payload[k] is None]

            if missing:
                st.error(f"Semua input harus diisi! Field kosong: {', '.join(missing)}")
            else:
                confirmation_dialog(payload, 'item_list_input_state')

# Show success banner after rerun if state is set
if st.session_state['item_list_input_state']:
    st.success("Item list baru berhasil di-input")
