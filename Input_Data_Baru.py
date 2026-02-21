import streamlit as st
import re
from data_integrator import is_exist
from element_component import confirmation_dialog_single_submission

st.set_page_config(
    page_title="Input Kategori, Warna, dan Item Baru",
    page_icon="➕"
)

st.sidebar.header("➕ Input Kategori, Warna, dan Item Baru")

if 'category_input_state' not in st.session_state:
    st.session_state['category_input_state'] = False

if 'color_input_state' not in st.session_state:
    st.session_state['color_input_state'] = False

if 'item_input_state' not in st.session_state:
    st.session_state['item_input_state'] = False


def validate_category_name(val):
    if is_exist("category", "category", val.title()):
        return False, f"Kategori '{val}' sudah ada di database"
    if not val:
        return False, f"Kategori tidak boleh kosong"
    if not re.match(r"^[A-Za-z\s'-]{2,50}$", val):
        return False, f"Kategori hanya boleh terdiri dari huruf, spasi, tanda hubung, atau tanda petik (2–50 karakter)."
    return True, ""


def validate_category_code(val):
    if not val:
        return False, f"Kode kategori tidak boleh kosong"
    if not re.match(r"^[A-Za-z]{2}$", val):
        return False, f"Kode kategori hanya boleh terdiri dari huruf (2 karakter)."
    if is_exist("category", "code", val.upper()):
        return False, f"Kode kategori '{val}' sudah ada di database"
    return True, ""


def validate_color_name(val):
    if not val:
        return False, f"Warna tidak boleh kosong"
    if not re.match(r"^[A-Za-z\s'-]{2,50}$", val):
        return False, f"Warna hanya boleh terdiri dari huruf, spasi, tanda hubung, garis bawah, atau tanda petik (2–50 karakter)."
    if is_exist("color", "color", val.title()):
        return False, f"Warna '{val}' sudah ada di database"
    return True, ""


def validate_item_name(val):
    if not val:
        return False, f"Item tidak boleh kosong"
    if not re.match(r"^[A-Za-z0-9\s'_-]{2,50}$", val):
        return False, f"Item hanya boleh terdiri dari huruf & angka, spasi, tanda hubung, atau tanda petik (2–50 karakter)."
    if is_exist("item_name", "item_name", val.title()):
        return False, f"Item '{val}' sudah ada di database"
    return True, ""


with st.form("category_input_form", enter_to_submit=False):
    st.subheader("Input Kategori Baru:")
    cat_name_input = st.text_input("Kategori")
    cat_code_input = st.text_input("Kode")

    submitted_cat = st.form_submit_button("Submit")

    if submitted_cat:
        st.session_state['category_input_state'] = False
        is_valid_name, message_name = validate_category_name(cat_name_input)
        is_valid_code, message_code = validate_category_code(cat_code_input)
        if not is_valid_name:
            st.error(message_name)
        if not is_valid_code:
            st.error(message_code)
        if is_valid_name and is_valid_code:
            confirmation_dialog_single_submission("category",
                                                  {"category": cat_name_input, "code": cat_code_input.upper()},
                                                  "category_input_state")

    if st.session_state['category_input_state']:
        st.success(f"Kategori Baru berhasil di-input")

with st.form("color_input_form", enter_to_submit=False):
    st.subheader("Input Warna Baru:")
    color_name_input = st.text_input("Warna")

    submitted_color = st.form_submit_button("Submit")

    if submitted_color:
        st.session_state['color_input_state'] = False
        is_valid_name, message_name = validate_color_name(color_name_input)
        if not is_valid_name:
            st.error(message_name)
        else:
            confirmation_dialog_single_submission("color", {"color": color_name_input}, "color_input_state")

    if st.session_state['color_input_state']:
        st.success(f"Warna Baru berhasil di-input")

with st.form("item_input_form", enter_to_submit=False):
    st.subheader("Input Item Baru:")
    item_name_input = st.text_input("Item")

    submitted = st.form_submit_button("Submit")

    if submitted:
        st.session_state['item_input_state'] = False
        is_valid_name, message_name = validate_item_name(item_name_input)
        if not is_valid_name:
            st.error(message_name)
        else:
            confirmation_dialog_single_submission("item_name", {"item_name": item_name_input}, "item_input_state")

    if st.session_state['item_input_state']:
        st.success(f"Item Baru berhasil di-input")
