import streamlit as st

def render_settings_panel(app_config=None):
    """Render the settings panel with toggles for display options."""
    if st.session_state.show_settings:
        with st.expander("Settings", expanded=True):
            # Get feature flags from app_config
            show_token_counting = app_config.get("features", {}).get("token_counting", True) if app_config else True
            
            # Callback functions to update state directly
            def toggle_cost():
                st.session_state.show_token_cost = not st.session_state.show_token_cost
                st.session_state.needs_rerun = True

            def toggle_context():
                st.session_state.show_context_usage = not st.session_state.show_context_usage
                st.session_state.needs_rerun = True

            # Only show token counting toggle if feature is enabled
            if show_token_counting:
                st.toggle("Show Token Count & Cost (Current Chat)", 
                         value=st.session_state.show_token_cost, 
                         key="show_token_cost_toggle", 
                         on_change=toggle_cost)
                
                st.toggle("Show Context Usage (Current Chat)", 
                         value=st.session_state.show_context_usage, 
                         key="show_context_usage_toggle", 
                         on_change=toggle_context)