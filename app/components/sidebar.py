import streamlit as st
from datetime import datetime
from utils.token_calculator import calculate_tokens, calculate_cost

def render_sidebar(available_llms_map, app_config=None):
    """Render the sidebar with chat history and LLM selection."""
    # Get feature flags from app_config
    show_model_selection = app_config.get("features", {}).get("model_selection", True) if app_config else True
    show_token_counting = app_config.get("features", {}).get("token_counting", True) if app_config else True
    show_file_upload = app_config.get("features", {}).get("file_upload", True) if app_config else True
    
    with st.sidebar:
        #st.header("Controls")

        # LLM Selector - only show if model selection is enabled
        if show_model_selection:
            available_llms_list = list(available_llms_map.keys())
            display_llms_list = ["None"] + available_llms_list
            
            try:
                selected_llm_index = display_llms_list.index(st.session_state.selected_llm)
            except ValueError:
                selected_llm_index = 0  # Default to "None" if current selection is invalid

            # Use callback for state update on selectbox change
            def update_llm_selection():
                st.session_state.selected_llm = st.session_state.selected_llm_widget

            st.selectbox("Select Language Model", options=display_llms_list, index=selected_llm_index, 
                        key="selected_llm_widget", on_change=update_llm_selection, 
                        help="Choose the language model to interact with.")
            
            if not available_llms_list:
                st.error("No LLM clients are configured or available. Please check config.yaml.")

        # File attachment form - only show if file upload is enabled
        if show_file_upload:
            with st.form(key=f"chat_form_{st.session_state.current_chat_id}", clear_on_submit=True):
                attach_label = " Attach Document " if not st.session_state.uploaded_file_name else f"{st.session_state.uploaded_file_name}"
                attach_help = "Attach a file" if not st.session_state.uploaded_file_name else f"File attached: {st.session_state.uploaded_file_name}"

                if st.form_submit_button(attach_label, help=attach_help, use_container_width=True, type="secondary"):
                    if st.session_state.uploaded_file_name:
                        # Clear attachment
                        st.session_state.uploaded_file_content = None
                        st.session_state.uploaded_file_name = None
                        st.toast("📎 Attachment removed.", icon="🗑️")
                    else:
                        # Toggle file uploader
                        st.session_state.show_file_uploader = not st.session_state.show_file_uploader

        st.divider()

        # Chat History
        st.header("Chat History")

        if st.button("➕ New Chat", use_container_width=True, help="Start a new conversation"):
            new_chat_id = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
            st.session_state.chats[new_chat_id] = {"title": "New Chat", "messages": []}
            st.session_state.current_chat_id = new_chat_id
            st.session_state.stop_streaming = False
            st.session_state.is_generating = False  # Ensure generating state is reset
            st.session_state.uploaded_file_content = None  # Clear any pending file
            st.session_state.uploaded_file_name = None

        with st.expander("Recent Chats", expanded=True):
            chat_ids = list(st.session_state.chats.keys())
            for chat_id in reversed(chat_ids):
                if chat_id not in st.session_state.chats:
                    continue  # Skip if deleted during iteration

                chat_info = st.session_state.chats[chat_id]
                title = chat_info.get("title", "New Chat")
                
                is_current = chat_id == st.session_state.current_chat_id

                # Use columns for title button and delete button
                col1, col2 = st.columns([5, 1])

                with col1:
                    if st.button(f"{title}", key=f"select_{chat_id}", use_container_width=True, 
                                type="primary" if is_current else "secondary", 
                                help=f"Switch to chat: {title}"):
                        if not is_current:
                            st.session_state.current_chat_id = chat_id
                            st.session_state.stop_streaming = False
                            st.session_state.is_generating = False
                            st.session_state.uploaded_file_content = None
                            st.session_state.uploaded_file_name = None
                with col2:
                    if st.button("🗑️", key=f"delete_{chat_id}", help="Delete this chat", use_container_width=True):
                        if len(st.session_state.chats) <= 1:
                            st.warning("Cannot delete the last chat.")
                        else:
                            # Find the next chat to select if we delete the current one
                            current_index = -1
                            ids_list = list(st.session_state.chats.keys())
                            try:
                                current_index = ids_list.index(chat_id)
                            except ValueError:
                                pass  # Should not happen

                            next_chat_id_to_select = None
                            if chat_id == st.session_state.current_chat_id:
                                if current_index > 0:
                                    next_chat_id_to_select = ids_list[current_index - 1]
                                elif current_index < len(ids_list) - 1:
                                    next_chat_id_to_select = ids_list[current_index + 1]

                            # Set delete request state for processing at top of script
                            st.session_state.delete_request = {"delete_id": chat_id, "next_id": next_chat_id_to_select}
                            st.session_state.needs_rerun = True

        # Usage Info Section (Conditional)
        if show_token_counting:
            st.divider()
            current_chat_messages = st.session_state.chats.get(st.session_state.current_chat_id, {}).get("messages", [])

            # Context Usage (Conditional Display)
            if st.session_state.show_context_usage:
                CONTEXT_WINDOW_SIZE = 128000  # This should be defined elsewhere and imported
                current_context_tokens = sum(calculate_tokens(msg["content"]) for msg in current_chat_messages)
                context_usage_percent = (current_context_tokens / CONTEXT_WINDOW_SIZE) * 100
                st.caption("Context Usage (Approx):")
                st.progress(min(context_usage_percent / 100.0, 1.0))
                st.caption(f"{current_context_tokens:,} / {CONTEXT_WINDOW_SIZE:,} tokens ({context_usage_percent:.1f}%)")
                st.divider()

            # Token/Cost Totals (Conditional Display)
            if st.session_state.show_token_cost:
                total_input_tokens = 0
                total_output_tokens = 0
                total_cost = 0.0

                for msg in current_chat_messages:
                    if msg["role"] == "user":
                        tokens = msg.get("input_tokens", calculate_tokens(msg["content"]))
                        total_input_tokens += tokens
                        total_cost += msg.get("input_cost", calculate_cost(tokens, "input"))
                    elif msg["role"] == "assistant":
                        tokens = msg.get("output_tokens", calculate_tokens(msg["content"]))
                        total_output_tokens += tokens
                        total_cost += msg.get("output_cost", calculate_cost(tokens, "output"))

                st.caption("Current Chat Totals (Approx):")
                st.caption(f"Input Tokens: {total_input_tokens:,}")
                st.caption(f"Output Tokens: {total_output_tokens:,}")
                st.caption(f"Estimated Cost: ${total_cost:.6f}")
            
                st.divider()