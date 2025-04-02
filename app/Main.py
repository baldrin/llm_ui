from datetime import datetime

import streamlit as st
import html

# Import utility functions
from utils.file_handler import load_config

# Import service layer
from services.llm_service import LLMService

# Import UI components
from components.sidebar import render_sidebar
from components.settings_panel import render_settings_panel
from components.chat_window import render_chat_window
from components.input_area import render_input_area
from components.llm_response_handler import handle_llm_response
from landing_page import render_landing_page


from config.app_configs import get_app_config

st.set_page_config(
    layout="wide",
    page_title="Mosaic Platform",
    page_icon="🧠"
    #page_icon="⚙️"
)

# Check if an app mode is specified in the URL
query_params = st.query_params
app_id = query_params.get("mode", None)

# If no app is selected, render the landing page
if app_id is None:
    render_landing_page()
    st.stop()  # Stop execution here if we're showing the landing page

#query_params = st.query_params
#app_id = query_params.get("mode", [None][0])
app_config = get_app_config(app_id)

dynamic_title = app_config["title"]
escape_title = html.escape(dynamic_title, quote="True")

st.markdown(
    f"""
    <script>
        document.title = "{escape_title}";
    </script>
    """,
    unsafe_allow_html=True,
)

# --- Initialize Session State ---
if "config" not in st.session_state: st.session_state.config = load_config()
# Initialize clients (errors handled within classes)
if "llm_service" not in st.session_state: st.session_state.llm_service = LLMService(st.session_state.config)
# Initialize needs_rerun flag
if "needs_rerun" not in st.session_state: st.session_state.needs_rerun = False
# Store current app in session state
if "current_app" not in st.session_state or st.session_state.current_app != app_id:
    st.session_state.current_app = app_id
    # Reset chat history when switching apps
    if "chats" in st.session_state:
        st.session_state.chats = {}

# Determine available LLMs *after* attempting init
available_llms_map = {}

if "llm_models" in st.session_state.config:
    for model_name, model_id in st.session_state.config["llm_models"].items():
        available_llms_map[model_name] = model_id  # st.session_state.llm_service

available_llms_list = [name for name, client in available_llms_map.items()]  # if client.is_available()]

# Default LLM selection logic
if "selected_llm" not in st.session_state:
    if available_llms_list:
        st.session_state.selected_llm = available_llms_list[0]  # Default to first available
    else:
        st.session_state.selected_llm = "None"
elif st.session_state.selected_llm not in available_llms_list and st.session_state.selected_llm != "None":
    st.session_state.selected_llm = available_llms_list[0] if available_llms_list else "None"  # Reset if previous selection invalid


if "chats" not in st.session_state:
    st.session_state.chats = {}
    # Ensure at least one chat exists
    if not st.session_state.chats:
        first_chat_id = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        st.session_state.chats[first_chat_id] = {"title": "New Chat", "messages": []}
        st.session_state.current_chat_id = first_chat_id
elif "current_chat_id" not in st.session_state or st.session_state.current_chat_id not in st.session_state.chats:
    # If current chat ID is invalid (e.g., after deletion), select the latest one
    if st.session_state.chats:
        st.session_state.current_chat_id = list(st.session_state.chats.keys())[-1]
    else:  # If no chats exist at all, create one
        first_chat_id = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        st.session_state.chats[first_chat_id] = {"title": "New Chat", "messages": []}
        st.session_state.current_chat_id = first_chat_id


# Other session state variables
if "show_settings" not in st.session_state: st.session_state.show_settings = False
if "show_token_cost" not in st.session_state: st.session_state.show_token_cost = False
if "show_context_usage" not in st.session_state: st.session_state.show_context_usage = False
if "stop_streaming" not in st.session_state: st.session_state.stop_streaming = False
if "is_generating" not in st.session_state: st.session_state.is_generating = False
if "uploaded_file_content" not in st.session_state: st.session_state.uploaded_file_content = None
if "uploaded_file_name" not in st.session_state: st.session_state.uploaded_file_name = None
if "delete_request" not in st.session_state: st.session_state.delete_request = None
if "show_file_uploader" not in st.session_state: st.session_state.show_file_uploader = False


# --- Global Variables/Constants ---
CONTEXT_WINDOW_SIZE = 128000

# --- Process Delete Request (Run Early) ---
if st.session_state.get("delete_request"):
    delete_info = st.session_state.pop("delete_request")
    delete_id = delete_info["delete_id"]
    next_id = delete_info["next_id"]  # This might be None if deleting the last available option

    if delete_id in st.session_state.chats:
        del st.session_state.chats[delete_id]
        st.toast("Chat deleted.", icon="🗑️")  # User feedback

    # If the deleted chat was the current one, switch
    if delete_id == st.session_state.current_chat_id:
        if next_id and next_id in st.session_state.chats:
            st.session_state.current_chat_id = next_id
        elif st.session_state.chats:  # Fallback to the latest remaining (keys are ordered by insertion)
            st.session_state.current_chat_id = list(st.session_state.chats.keys())[-1]
        else:  # If all chats somehow got deleted (shouldn't happen with the guard)
            first_chat_id = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            st.session_state.chats[first_chat_id] = {"title": "New Chat", "messages": []}
            st.session_state.current_chat_id = first_chat_id
    
    # Set needs_rerun flag instead of immediate rerun
    st.session_state.needs_rerun = True


# --- UI Rendering ---

# Settings Toggle Button
col1, col2 = st.columns([10, 1])
with col1:
    effective_llm = st.session_state.selected_llm if st.session_state.selected_llm != "None" else "No LLM Selected"
    st.title(f"{app_config['title']}")
with col2:
    if st.button("⚙️", key="settings_toggle", help="Open Settings"):
        st.session_state.show_settings = not st.session_state.show_settings

# Add a "Back to Apps" button
#if st.button("← Back to Apps", key="back_to_apps"):
#    st.rerun()

# Render Settings Panel
render_settings_panel(app_config=app_config)

# Render Sidebar
render_sidebar(available_llms_map, app_config=app_config)

# Render Chat Window
render_chat_window()

# Render Input Area
render_input_area(app_config=app_config)

# Handle LLM Response
handle_llm_response(available_llms_map, app_config=app_config)

# Single rerun point - if any component set the needs_rerun flag
if st.session_state.needs_rerun:
    st.session_state.needs_rerun = False
    st.rerun()