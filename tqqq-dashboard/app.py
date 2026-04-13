import streamlit as st
st.set_page_config(
    page_title="Play the Dip Lab",
    page_icon="bar_chart",
    layout="wide",
)

from grid_search_view import render as render_grid_search
from home_view import render as render_home


navigation = st.navigation(
    [
        st.Page(render_home, title="Home", url_path="home", default=True),
        st.Page(render_grid_search, title="Grid Search", url_path="grid-search"),
    ]
)
navigation.run()
