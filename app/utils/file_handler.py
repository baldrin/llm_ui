import html
import json
import streamlit as st

def load_config(config_path="config.json"):
    """Load configuration from JSON file."""
    try:
        with open(config_path, "r") as f:
            config_data = json.load(f)
        return config_data
    except FileNotFoundError:
        st.error(f"Configuration file '{config_path}' not found.")
        st.stop()
    except Exception as e:
        st.error(f"Error loading configuration: {e}")
        st.stop()

def format_file_content(file_name, file_content):
    """Format file content for display in chat with proper HTML structure."""
    escaped_name = html.escape(file_name)
    escaped_content = html.escape(file_content)
    
    return f"""<details><summary>📎 Attached File: {escaped_name}</summary><div style="white-space: pre-wrap;">{escaped_content}</div></details>"""
