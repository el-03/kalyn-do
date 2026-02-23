import streamlit as st
from data_integrator import insert_row
import pandas as pd


@st.dialog("Konfirmasi")
def confirmation_dialog_single_submission(name, value, state_name):
    df = pd.DataFrame(value.items(), columns=["Key", "Value"])
    st.dataframe(df, hide_index=True)

    col_yes, col_no = st.columns(2)

    with col_yes:
        if st.button("Ya", type="primary", key="confirm_yes"):
            status, msg, data = insert_row(name, value)
            st.session_state[state_name] = status

            if not status:
                st.error(msg)
            else:
                st.rerun()
    with col_no:
        if st.button("Tidak"):
            st.rerun()
