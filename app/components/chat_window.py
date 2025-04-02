import streamlit as st

def render_chat_window():
    """Render the main chat window with message history."""
    chat_container = st.container()
    
    with chat_container:
        # Initialize greeting flag for this chat if needed
        current_chat_id = st.session_state.current_chat_id
        if f"greeting_shown_{current_chat_id}" not in st.session_state:
            st.session_state[f"greeting_shown_{current_chat_id}"] = False
        
        # Get app config
        app_id = st.session_state.get("current_app", "assistant")
        from config.app_configs import get_app_config
        app_config = get_app_config(app_id)
        
        # Always display welcome message at the top
        # Add a visual separator between welcome and conversation
    
        with st.chat_message("assistant"):
            if app_id == "assistant":
                welcome_message = f"👋 Welcome to the {app_config['title']}! How can I help you today?"
            elif app_id == "coach":
                welcome_message = f"👋 Welcome to the {app_config['title']}! I'm here to help you explore your leadership challenges through thoughtful questions. What would you like to discuss today?"
            elif app_id == "letter_generator":
                welcome_message = f"👋 Welcome to the {app_config['title']}! I will convert complex medical notes into an easy to read letter."
            else:
                welcome_message = f"👋 Welcome! How can I assist you?"

            st.markdown(welcome_message)
            #st.markdown("<hr style='margin: 10px 0; opacity: 0.3;'>", unsafe_allow_html=True)
            
            # Mark greeting as shown for this chat
            st.session_state[f"greeting_shown_{current_chat_id}"] = True
        
        # Display actual chat messages (these are sent to LLM)
        if st.session_state.current_chat_id in st.session_state.chats:
            messages = st.session_state.chats[st.session_state.current_chat_id]["messages"]
            for msg in messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"], unsafe_allow_html=True)
        else:
            st.warning("Selected chat not found. Please select another chat or start a new one.")
            # Optionally select the latest chat automatically
            if st.session_state.chats:
                st.session_state.current_chat_id = list(st.session_state.chats.keys())[-1]
                st.session_state.needs_rerun = True  # Use needs_rerun instead of direct rerun