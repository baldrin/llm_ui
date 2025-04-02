import streamlit as st
from utils.token_calculator import calculate_tokens, calculate_cost
from utils.file_handler import format_file_content

def render_input_area(app_config=None):
    """Render the user input area with file upload functionality."""
    # Use app_config to control feature visibility
    show_file_upload = app_config.get("features", {}).get("file_upload", True) if app_config else True
   
    # Container for elements above the chat input
    input_controls_container = st.container()
    
    with input_controls_container:
        # Only show file uploader if feature is enabled
        if show_file_upload and st.session_state.show_file_uploader and not st.session_state.is_generating:
            uploaded_file = st.file_uploader(
                "Attach File",
                key=f"file_uploader_{st.session_state.current_chat_id}",
                help="Attach a text-based file (TXT, MD, PY, etc.). Content will be added to your next message.",
                label_visibility="collapsed",
                on_change=None,
            )

            if uploaded_file is not None:
                # Store content immediately if a new file is uploaded
                try:
                    st.session_state.uploaded_file_content = uploaded_file.read().decode("utf-8")
                    st.session_state.uploaded_file_name = uploaded_file.name
                    st.session_state.show_file_uploader = False
                    # Need rerun to update UI after file upload
                    st.session_state.needs_rerun = True
                except Exception as e:
                    st.error(f"Error reading file: {e}")
                    st.session_state.uploaded_file_content = None
                    st.session_state.uploaded_file_name = None
        
        # Show attachment indicator if file is ready to be sent
        elif show_file_upload and st.session_state.uploaded_file_content and st.session_state.uploaded_file_name:
            st.success(f"📎 File attached: {st.session_state.uploaded_file_name} (will be sent with your next message)")
            if st.button("❌ Remove attachment"):
                st.session_state.uploaded_file_content = None
                st.session_state.uploaded_file_name = None
                # Need rerun to update UI after removing attachment
                st.session_state.needs_rerun = True

    # Chat Input Box
    prompt = st.chat_input(
        "Enter your message here...", 
        key=f"chat_input_{st.session_state.current_chat_id}", 
        disabled=st.session_state.is_generating
    )

    if prompt:
        if st.session_state.selected_llm == "None":
            st.error("Please select an available LLM from the sidebar before sending a message.")
        else:
            st.session_state.stop_streaming = False  # Ensure stop flag is reset

            # Handle File Attachment (One-Time)
            full_prompt = prompt
            if st.session_state.uploaded_file_content and st.session_state.uploaded_file_name:
                # Use the utility function to format file content
                file_info = format_file_content(
                    st.session_state.uploaded_file_name,
                    st.session_state.uploaded_file_content
                )
                
                # Put file info first, then the user's message
                full_prompt = file_info + prompt

                st.session_state.uploaded_file_content = None
                st.session_state.uploaded_file_name = None
            
            # Append user message & calculate costs
            input_tokens = calculate_tokens(full_prompt)
            input_cost = calculate_cost(input_tokens, "input")
            user_message = {
                "role": "user", 
                "content": full_prompt, 
                "input_tokens": input_tokens, 
                "input_cost": input_cost, 
                "llm_provider": st.session_state.selected_llm
            }
            st.session_state.chats[st.session_state.current_chat_id]["messages"].append(user_message)

            # Display user message immediately
            with st.chat_message("user"):
                st.markdown(full_prompt, unsafe_allow_html=True)

            # Set generating flag and trigger rerun to start response generation
            st.session_state.is_generating = True
            st.session_state.needs_rerun = True