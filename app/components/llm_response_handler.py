import streamlit as st
from utils.token_calculator import calculate_tokens, calculate_cost
from utils.chat_utils import get_chat_title, generate_title_with_llm
from config.app_configs import get_app_config 

def handle_llm_response(available_llms_map, app_config=None):
    """Handle LLM response generation and streaming."""
    CONTEXT_WINDOW_SIZE = 128000  # This should be defined elsewhere

    system_prompt = app_config.get("system_prompt", None) if app_config else None

    #print(f"System Prompt: {system_prompt}\n")

    if st.session_state.is_generating:
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = ""
            response_stream = None
            assistant_message_content = ""  # Store final content for state update

            try:
                # Prepare message history
                llm_messages = []

                if system_prompt:
                    llm_messages.append({"role": "system", "content": system_prompt})

                # Add conversation messages
                llm_messages.extend([
                    {"role": m["role"], "content": m["content"]} 
                    for m in st.session_state.chats[st.session_state.current_chat_id]["messages"]
                ])

                #llm_messages = [
                #    {"role": m["role"], "content": m["content"]} 
                #    for m in st.session_state.chats[st.session_state.current_chat_id]["messages"]
                #]

                # Check context window
                total_prompt_tokens = sum(calculate_tokens(m["content"]) for m in llm_messages)
                if total_prompt_tokens >= CONTEXT_WINDOW_SIZE:
                    st.error(f"Context window limit (~{CONTEXT_WINDOW_SIZE} tokens) approached. Please start a new chat.")
                    assistant_message_content = f"Error: Context window limit reached ({total_prompt_tokens}/{CONTEXT_WINDOW_SIZE} tokens)."

                else:
                    # Dispatch to selected LLM
                    current_llm = st.session_state.selected_llm
                    llm_model = available_llms_map.get(current_llm)

                    if st.session_state.llm_service:
                        response_stream = st.session_state.llm_service.generate_completion(
                            messages=llm_messages,
                            stream=True,
                            llm_model=llm_model,
                        )
                    elif current_llm != "None":
                        st.error(f"{current_llm} client not available or not configured correctly.")
                        assistant_message_content = f"Error: Could not connect to {current_llm}."

                    # Stream Processing
                    if response_stream:
                        for chunk in response_stream:
                            if st.session_state.stop_streaming:
                                st.warning("Generation stopped by user.")
                                break
                            content_part = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta else None
                            if content_part:
                                full_response += content_part
                                message_placeholder.markdown(full_response + "▌")

                        # Final display without cursor
                        message_placeholder.markdown(full_response)
                        assistant_message_content = full_response
                        if st.session_state.stop_streaming:
                            assistant_message_content += " [Stopped by user]"
                            message_placeholder.markdown(assistant_message_content)

                    elif not assistant_message_content:  # If stream failed and no error message set yet
                        assistant_message_content = f"Error generating response with {current_llm}."
                        message_placeholder.error(assistant_message_content)

            except ConnectionError as e:
                st.error(f"Client Connection Error: {e}")
                assistant_message_content = f"Error: Could not connect to {st.session_state.selected_llm}."
                message_placeholder.error(assistant_message_content)
            except ValueError as e:
                st.error(f"Configuration Error: {e}")
                assistant_message_content = f"Error: Configuration issue for {st.session_state.selected_llm}."
                message_placeholder.error(assistant_message_content)
            except Exception as e:
                st.error(f"Error during streaming with {st.session_state.selected_llm}: {e}")
                print(f"Error during streaming with {st.session_state.selected_llm}: {e}")
                assistant_message_content = f"Sorry, an error occurred while generating the response using {st.session_state.selected_llm}."
                message_placeholder.error(assistant_message_content)
            finally:
                # Append assistant response (even if partial/error)
                if assistant_message_content:
                    output_tokens = calculate_tokens(assistant_message_content)
                    output_cost = calculate_cost(output_tokens, "output")
                    assistant_message = {
                        "role": "assistant",
                        "content": assistant_message_content,
                        "output_tokens": output_tokens,
                        "output_cost": output_cost,
                        "llm_provider": st.session_state.selected_llm,
                    }
                    st.session_state.chats[st.session_state.current_chat_id]["messages"].append(assistant_message)

                    # Update chat title if it was the first proper exchange
                    # In llm_response_handler.py
                    current_chat_messages = st.session_state.chats[st.session_state.current_chat_id]["messages"]
                    if st.session_state.chats[st.session_state.current_chat_id]["title"] == "New Chat" and len(current_chat_messages) > 1:
                        try:
                            # Try to generate title with LLM
                            current_llm = st.session_state.selected_llm
                            llm_model = available_llms_map.get(current_llm)
                            title = generate_title_with_llm(current_chat_messages, llm_model, st.session_state.llm_service)
                            st.session_state.chats[st.session_state.current_chat_id]["title"] = title
                        except Exception as e:
                            # Fallback to simple title if LLM generation fails
                            print(f"Error generating title with LLM: {e}")
                            st.session_state.chats[st.session_state.current_chat_id]["title"] = get_chat_title(current_chat_messages)

                # Reset states and set needs_rerun instead of calling rerun directly
                st.session_state.is_generating = False
                st.session_state.stop_streaming = False
                st.session_state.needs_rerun = True