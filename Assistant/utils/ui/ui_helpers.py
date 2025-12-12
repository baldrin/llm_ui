"""
UI helper functions for Streamlit interface customization.
"""
import base64
import streamlit as st
from pathlib import Path


def hide_streamlit_ui() -> None:
    """
    Hide default Streamlit UI elements including error dialog buttons.
    
    This function injects custom CSS to hide:
    - Main menu
    - Footer
    - Header
    - Error dialog action buttons
    
    Also fixes word wrapping in code blocks.
    """
    hide_menu_style = """
        <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        
        /* Hide the "Ask Google" and "Ask ChatGPT" buttons in error dialogs */
        .stException > div[data-testid="stMarkdownContainer"] > div > div > div > div:last-child {
            display: none !important;
        }
        
        /* Alternative selector for error dialog buttons */
        div[data-testid="stException"] button {
            display: none !important;
        }
        
        /* Hide error dialog footer with buttons */
        .stException .element-container:last-child {
            display: none !important;
        }
        
        /* Fix word wrapping in code blocks globally */
        .stMarkdown code {
            white-space: pre-wrap !important;
            word-wrap: break-word !important;
            overflow-wrap: break-word !important;
            max-width: 100% !important;
        }
        
        .stMarkdown pre {
            white-space: pre-wrap !important;
            word-wrap: break-word !important;
            overflow-wrap: break-word !important;
            max-width: 100% !important;
            overflow-x: auto !important;
        }
        
        .stMarkdown pre code {
            white-space: pre-wrap !important;
            word-wrap: break-word !important;
            overflow-wrap: break-word !important;
        }
        </style>
        """
    st.markdown(hide_menu_style, unsafe_allow_html=True)


def get_base64_of_image(image_path: str | Path) -> str:
    """Convert an image file to base64 encoding."""
    path = Path(image_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")
    
    try:
        with open(path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    except Exception as e:
        raise IOError(f"Error reading image file {image_path}: {e}")