# landing_page_renderer.py
import streamlit as st

def render_landing_page():
    """Render the landing page with properly sized cards and visible buttons"""
    
    st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        text-align: center;
        margin-bottom: 1.5rem;
    }
    .app-description {
        font-size: 1.1rem;
        text-align: center;
        margin-bottom: 2rem;
        max-width: 700px;
        margin-left: auto;
        margin-right: auto;
    }
    .app-container {
        display: flex;
        justify-content: center;
        gap: 20px;
        flex-wrap: nowrap; /* Changed from wrap to nowrap */
        max-width: 1200px; /* Increased max-width to accommodate all cards */
        margin: 0 auto;
    }
    .app-card {
        border-radius: 8px;
        padding: 20px;
        margin: 10px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.2);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
        width: calc(33.33% - 20px); /* Use percentage width instead of fixed width */
        min-width: 250px; /* Set minimum width */
        display: flex;
        flex-direction: column;
        border: 1px solid rgba(128, 128, 128, 0.2);
    }
    .app-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 5px 15px rgba(0,0,0,0.2);
    }
    .app-icon {
        font-size: 2.5rem;
        text-align: center;
        margin-bottom: 0.8rem;
    }
    .app-title {
        font-size: 1.3rem;
        font-weight: bold;
        text-align: center;
        margin-bottom: 0.8rem;
    }
    .app-card-description {
        flex-grow: 1;
        text-align: center;
        margin-bottom: 1.2rem;
        font-size: 0.95rem;
    }
    .app-button {
        background-color: #FF4B4B; /* Streamlit primary red color */
        border: none;
        border-radius: 4px;
        padding: 8px 16px;
        text-align: center;
        display: block;
        width: 80%;
        max-width: 180px;
        font-size: 1rem;
        margin: 0 auto;
        cursor: pointer;
        transition: background-color 0.2s ease;
        color: white !important;           /* Force white text */
        font-weight: 600 !important;       /* Force semi-bold text */
        text-decoration: none !important;  /* Force no underline */
    }
    .app-button:hover {
        background-color: #F63366; /* Slightly darker shade on hover */
        box-shadow: 0 2px 5px rgba(0,0,0,0.2);
        text-decoration: none !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.markdown('<div class="main-header">Welcome to the Mosaic Platform</div>', unsafe_allow_html=True)
    st.markdown('<div class="app-description">Choose an application to get started with our AI-powered tools</div>', unsafe_allow_html=True)
    
    # Use a container div to center the cards
    st.markdown('<div class="app-container">', unsafe_allow_html=True)
    
    # App cards
    st.markdown("""
    <div class="app-card">
        <div class="app-icon">🧠</div>
        <div class="app-title">Developer Assistant</div>
        <div class="app-card-description">
            General-purpose AI assistant for answering questions, generating content, and helping with various tasks.
        </div>
        <a href="?mode=assistant" target="_self" class="app-button">Launch Assistant</a>
    </div>
      
    <div class="app-card">
        <div class="app-icon">💬</div>
        <div class="app-title">Executive Coach</div>
        <div class="app-card-description">
            AI-powered leadership coaching to help you develop your skills through thoughtful questions and guidance.
        </div>
        <a href="?mode=coach" target="_self" class="app-button">Launch Coach</a>
    </div>
                
    <div class="app-card">
        <div class="app-icon">📧</div>
        <div class="app-title">Denial Letter Generator</div>
        <div class="app-card-description">
            Transforms complex medical notes into clear, patient-friendly letters written at a 6th grade reading level.
        </div>
        <a href="?mode=letter_generator" target="_self" class="app-button">Launch Letter Generator</a>
    </div>
    """, unsafe_allow_html=True)
    
    # Close the container
    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    # This allows testing the landing page independently
    st.set_page_config(page_title="Mosaic Platform", page_icon="🧩", layout="wide")
    render_landing_page()