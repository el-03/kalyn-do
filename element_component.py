import streamlit as st
from data_integrator import insert_row
import pandas as pd


@st.dialog("Konfirmasi")
def confirmation_dialog_single_submission(name, value, state_name):
    df = pd.DataFrame(value.items(), columns=["Key", "Value"])
    st.dataframe(df, hide_index=True)

    if st.button("Ya"):
        status, msg, data = insert_row(name, value)
        st.session_state[state_name] = status

        if not status:
            st.error(msg)
        else:
            st.rerun()
    if st.button("Tidak"):
        st.rerun()


@st.dialog("Berhasil")
def success_dialog():
    st.write('Berhasil di input')
    if st.button("Ya"):
        st.write("OK")
    if st.button("Tidak"):
        st.write("No")