import streamlit as st
import openai
import httpx
import yaml
import os
from datetime import datetime
import google.generativeai as genai
from collections.abc import Generator

# --- Configuration Loading (Keep As-Is) ---
def load_config(config_path="config.yaml"):
    try:
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
            config_data.setdefault('google_api_key', None)
            config_data.setdefault('gemini_model_name', 'gemini-1.5-flash-latest')
            config_data.setdefault('databricks_certs', None)
            config_data.setdefault('llm_auth_token', None)
            config_data.setdefault('base_url', None)
            config_data.setdefault('llm_model', None)
            config_data.setdefault('openai_api_key', None)
            config_data.setdefault('openai_model', 'gpt-3.5-turbo')
            return config_data
    except FileNotFoundError:
        st.error(f"Configuration file '{config_path}' not found.")
        st.stop()
    except Exception as e:
        st.error(f"Error loading configuration: {e}")
        st.stop()

# --- LLM Clients (Keep As-Is) ---
class DatabricksLLMClient:
    # ... (previous DatabricksLLMClient code) ...
    def __init__(self, config):
        self.client = None
        self.llm_model = config.get('llm_model')

        # Only initialize if config is present
        if not config.get('llm_auth_token') or not config.get('base_url') or not config.get('llm_model'):
            # st.warning("Databricks configuration incomplete. Databricks LLM unavailable.", icon="⚠️") # Quieter for library use
            return
        if not config.get('databricks_certs') or not os.path.exists(config['databricks_certs']):
            # st.warning(f"Databricks certificate not found at {config.get('databricks_certs')}. Databricks LLM unavailable.", icon="⚠️")
             self.cert_error = True # Flag issue
             return
        else:
             self.cert_error = False


        try:
            http_client = httpx.Client(verify=config['databricks_certs'])
            self.client = openai.OpenAI(
                api_key=config['llm_auth_token'],
                base_url=config['base_url'],
                http_client=http_client
            )
        except Exception as e:
            st.error(f"Error initializing Databricks Client: {e}")
            self.client = None # Ensure client is None on error

    def is_available(self):
        # Also check for cert error flagged during init
        if hasattr(self, 'cert_error') and self.cert_error:
             return False
        return self.client is not None

    def generate_completion(self, messages, temperature=0.5, max_tokens=4096, stream=False, llm_model=None):
        if not self.is_available():
             # Add more specific error if cert related
             if hasattr(self, 'cert_error') and self.cert_error:
                  raise ConnectionError("Databricks certificate missing or invalid. Client unavailable.")
             raise ConnectionError("Databricks client not available or not configured correctly.")


        model_to_use = llm_model if llm_model else self.llm_model
        if not model_to_use:
            raise ValueError("Databricks LLM model name not configured.")

        try:
            return self.client.chat.completions.create(
                model=model_to_use,
                messages=messages,
                temperature=temperature,
                # max_tokens=max_tokens, # Check if your DB endpoint supports it
                stream=stream
            )
        # Keep specific error handling
        except openai.APIConnectionError as e:
             st.error(f"Databricks API Connection Error: {e}. Check Base URL and network.")
        except openai.AuthenticationError as e:
             st.error(f"Databricks Authentication Error: {e}. Check your API Key (Databricks PAT).")
        except openai.RateLimitError as e:
             st.error(f"Databricks Rate Limit Error: {e}.")
        except openai.APIStatusError as e:
             st.error(f"Databricks API Error: Status={e.status_code}, Response={e.response.text}")
        except Exception as e:
            st.error(f"An unexpected error occurred during Databricks LLM call: {e}")
        return None # Return None on error

class OpenAIClient:
    # ... (previous OpenAIClient code) ...
    def __init__(self, config):
        self.client = None
        self.model_name = config.get('openai_model', 'gpt-3.5-turbo')
        self.api_key = config.get('openai_api_key')

        if not self.api_key:
            # st.warning("OpenAI API Key not found in config. OpenAI unavailable.", icon="⚠️")
            return

        try:
            self.client = openai.OpenAI(api_key=self.api_key)
        except Exception as e:
            st.error(f"Error initializing OpenAI Client: {e}")
            self.client = None

    def is_available(self):
        return self.client is not None

    def generate_completion(self, messages, temperature=0.7, max_tokens=4096, stream=False):
        if not self.is_available():
            raise ConnectionError("OpenAI client not available or not configured correctly.")

        try:
            return self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream
            )
        except openai.APIConnectionError as e:
            st.error(f"OpenAI API Connection Error: {e}")
        except openai.AuthenticationError as e:
            st.error(f"OpenAI Authentication Error: {e}")
        except openai.RateLimitError as e:
            st.error(f"OpenAI Rate Limit Error: {e}")
        except Exception as e:
            st.error(f"An unexpected error occurred during OpenAI LLM call: {e}")
        return None

class GeminiClient:
    # ... (previous GeminiClient code) ...
    def __init__(self, config):
        self.client = None
        self.model_name = config.get('gemini_model_name', 'gemini-1.5-flash-latest')
        self.api_key = config.get('google_api_key')

        if not self.api_key:
            # st.warning("Google API Key not found in config. Gemini unavailable.", icon="⚠️")
            return

        try:
            genai.configure(api_key=self.api_key)
            self.client = genai.GenerativeModel(self.model_name)
        except Exception as e:
            st.error(f"Error initializing Google Gemini Client: {e}")
            self.client = None

    def is_available(self):
        return self.client is not None

    # Convert OpenAI message format to Gemini format
    def _convert_messages_to_gemini(self, messages):
        # ... (keep previous _convert_messages_to_gemini code) ...
        gemini_history = []
        current_content = []
        current_role = None
        for msg in messages:
            role = msg['role']
            content = msg['content']
            if role == "assistant":
                role = "model"
            elif role not in ["user", "model"]:
                continue
            if current_role == role:
                 current_content.append(content)
            else:
                if current_role and current_content:
                    gemini_history.append({"role": current_role, "parts": ["\n".join(current_content)]})
                current_role = role
                current_content = [content]
        if current_role and current_content:
            gemini_history.append({"role": current_role, "parts": ["\n".join(current_content)]})
        # if gemini_history and gemini_history[0]['role'] != 'user':
             # st.warning("Chat history doesn't start with a user message. Gemini might behave unexpectedly.", icon="⚠️")
        return gemini_history


    # Adapt generate_completion for Gemini
    def generate_completion(self, messages, temperature=0.7, max_tokens=None, stream=False):
        if not self.is_available():
            raise ConnectionError("Gemini client not available or not configured correctly.")
        gemini_messages = self._convert_messages_to_gemini(messages)
        if not gemini_messages:
            return None
        generation_config = genai.types.GenerationConfig(
             temperature=temperature,
        )
        try:
            if stream:
                response_stream = self.client.generate_content(
                    gemini_messages,
                    stream=True,
                    generation_config=generation_config
                )
                return self._adapt_gemini_stream(response_stream)
            else:
                st.error("Non-streaming Gemini not implemented in this example.")
                return None
        except Exception as e:
            # Be more specific about potential Gemini API errors if possible
            # Example: Handle BlockedPromptError, ContentFilterError, etc.
            st.error(f"An error occurred during Gemini LLM call: {e}")
            # Log the specific error type if needed: print(f"Gemini Error Type: {type(e)}")
            return None

    # Adapter function to make Gemini stream look like OpenAI stream for the UI loop
    def _adapt_gemini_stream(self, gemini_stream) -> Generator:
        # ... (keep previous _adapt_gemini_stream code) ...
        class MockChoiceDelta:
            def __init__(self, content):
                self.content = content
        class MockChoice:
            def __init__(self, delta):
                self.delta = delta
        class MockStreamChunk:
            def __init__(self, choice):
                self.choices = [choice]
        try:
            for chunk in gemini_stream:
                # Check for safety ratings/blocks if needed
                # if chunk.prompt_feedback.block_reason:
                #     st.error(f"Gemini API Blocked: {chunk.prompt_feedback.block_reason}")
                #     # yield appropriate message or raise error
                #     delta = MockChoiceDelta(f"\n\n[Blocked by API: {chunk.prompt_feedback.block_reason}]")

                # Normal text processing
                if hasattr(chunk, 'text'):
                     delta = MockChoiceDelta(chunk.text)
                     choice = MockChoice(delta)
                     yield MockStreamChunk(choice)

        except Exception as e:
             st.error(f"Error processing Gemini stream chunk: {e}")
             delta = MockChoiceDelta(f"\n\n[Error processing stream: {e}]")
             choice = MockChoice(delta)
             yield MockStreamChunk(choice)


# --- Helper Functions ---
def calculate_tokens(text):
    return len(text) // 4

def calculate_cost(tokens, type="input", llm_provider="Databricks"):
    # ... (keep previous cost calculation logic) ...
    if llm_provider == "Databricks":
        cost_per_million = 3 if type == "input" else 15
        return (tokens / 1_000_000) * cost_per_million
    elif llm_provider == "Gemini Flash":
        return 0.0
    elif llm_provider == "OpenAI":
        cost_per_million = 0.5 if type == "input" else 1.5 # Example pricing for gpt-3.5-turbo
        return (tokens / 1_000_000) * cost_per_million
    else:
        return 0.0

def get_chat_title(messages):
    for msg in messages:
        if msg["role"] == "user":
            # Strip potential file attachment markers for cleaner titles
            content = msg["content"]
            if content.startswith("[Attached File:"):
                end_marker = "[End of File:"
                end_idx = content.find(end_marker)
                if end_idx != -1:
                    post_file_content = content[end_idx + len(end_marker):].split("\n", 1)[-1].strip()
                    content = post_file_content if post_file_content else "Chat with file" # Use content after file or generic title
            title = content[:30]
            return title + ("..." if len(content) > 30 else "")
    return "New Chat"

# --- Streamlit App ---

st.set_page_config(layout="wide")

# --- Initialize Session State ---
if "config" not in st.session_state:
    st.session_state.config = load_config()
# Initialize clients (errors handled within classes)
if "databricks_client" not in st.session_state:
    st.session_state.databricks_client = DatabricksLLMClient(st.session_state.config)
if "gemini_client" not in st.session_state:
    st.session_state.gemini_client = GeminiClient(st.session_state.config)
if "openai_client" not in st.session_state:
    st.session_state.openai_client = OpenAIClient(st.session_state.config)

# Determine available LLMs *after* attempting init
available_llms_map = {
    "OpenAI": st.session_state.openai_client,
    "Gemini Flash": st.session_state.gemini_client,
    "Databricks": st.session_state.databricks_client,
}
available_llms_list = [name for name, client in available_llms_map.items() if client.is_available()]

# Default LLM selection logic
if "selected_llm" not in st.session_state:
    if available_llms_list:
        st.session_state.selected_llm = available_llms_list[0] # Default to first available
    else:
        st.session_state.selected_llm = "None"
elif st.session_state.selected_llm not in available_llms_list and st.session_state.selected_llm != "None":
     st.session_state.selected_llm = available_llms_list[0] if available_llms_list else "None" # Reset if previous selection invalid


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
     else: # If no chats exist at all, create one
        first_chat_id = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        st.session_state.chats[first_chat_id] = {"title": "New Chat", "messages": []}
        st.session_state.current_chat_id = first_chat_id


# Other session state variables
if "show_settings" not in st.session_state:
    st.session_state.show_settings = False
if "show_token_cost" not in st.session_state:
    st.session_state.show_token_cost = False
if "show_context_usage" not in st.session_state: # New setting state
    st.session_state.show_context_usage = False
if "stop_streaming" not in st.session_state:
    st.session_state.stop_streaming = False
if "is_generating" not in st.session_state: # New state for stop button visibility
    st.session_state.is_generating = False
if "uploaded_file_content" not in st.session_state: # New state for one-time file attachment
    st.session_state.uploaded_file_content = None
if "uploaded_file_name" not in st.session_state:
    st.session_state.uploaded_file_name = None
if "delete_request" not in st.session_state: # For handling delete clicks
     st.session_state.delete_request = None


# --- Global Variables/Constants ---
CONTEXT_WINDOW_SIZE = 128000

# --- Process Delete Request (Run Early) ---
if st.session_state.get("delete_request"):
    delete_info = st.session_state.pop("delete_request")
    delete_id = delete_info["delete_id"]
    next_id = delete_info["next_id"] # This might be None if deleting the last available option

    if delete_id in st.session_state.chats:
        del st.session_state.chats[delete_id]
        st.toast(f"Chat deleted.", icon="🗑️") # User feedback

    # If the deleted chat was the current one, switch
    if delete_id == st.session_state.current_chat_id:
        if next_id and next_id in st.session_state.chats:
            st.session_state.current_chat_id = next_id
        elif st.session_state.chats: # Fallback to the latest remaining (keys are ordered by insertion)
            st.session_state.current_chat_id = list(st.session_state.chats.keys())[-1]
        else: # If all chats somehow got deleted (shouldn't happen with the guard)
            first_chat_id = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            st.session_state.chats[first_chat_id] = {"title": "New Chat", "messages": []}
            st.session_state.current_chat_id = first_chat_id
    # No rerun needed here, it was triggered by the delete button click


# --- UI Rendering ---

# Settings Toggle Button
col1, col2 = st.columns([10, 1])
with col1:
    effective_llm = st.session_state.selected_llm if st.session_state.selected_llm != "None" else "No LLM Selected"
    st.title(f"LLM Chat Interface ({effective_llm})")
with col2:
    if st.button("⚙️", key="settings_toggle", help="Open Settings"):
        st.session_state.show_settings = not st.session_state.show_settings

# Settings Panel
if st.session_state.show_settings:
    with st.expander("Settings", expanded=True):
        # Callback functions to update state directly
        def toggle_cost():
            st.session_state.show_token_cost = not st.session_state.show_token_cost
        def toggle_context():
            st.session_state.show_context_usage = not st.session_state.show_context_usage

        st.toggle(
            "Show Token Count & Cost (Current Chat)",
            value=st.session_state.show_token_cost,
            key="show_token_cost_toggle",
            on_change=toggle_cost
        )
        st.toggle(
            "Show Context Usage (Current Chat)", # New toggle
            value=st.session_state.show_context_usage,
            key="show_context_usage_toggle",
            on_change=toggle_context
        )

# Sidebar for Chat History & LLM Selection
with st.sidebar:
    st.header("Controls")

    # LLM Selector
    display_llms_list = ["None"] + available_llms_list
    try:
        selected_llm_index = display_llms_list.index(st.session_state.selected_llm)
    except ValueError:
        selected_llm_index = 0 # Default to "None" if current selection is invalid


    # Use callback for state update on selectbox change
    def update_llm_selection():
        st.session_state.selected_llm = st.session_state.selected_llm_widget

    st.selectbox(
        "Select LLM",
        options=display_llms_list,
        index=selected_llm_index,
        key="selected_llm_widget",
        on_change=update_llm_selection,
        help="Choose the language model to interact with."
    )
    if not available_llms_list:
        st.error("No LLM clients are configured or available. Please check config.yaml.")

    st.divider()

    # Chat History
    st.header("Chat History")
    if st.button("➕ New Chat", use_container_width=True, help="Start a new conversation"):
        new_chat_id = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        st.session_state.chats[new_chat_id] = {"title": "New Chat", "messages": []}
        st.session_state.current_chat_id = new_chat_id
        st.session_state.stop_streaming = False
        st.session_state.is_generating = False # Ensure generating state is reset
        st.session_state.uploaded_file_content = None # Clear any pending file
        st.session_state.uploaded_file_name = None
        st.rerun()

    # Display existing chats, using insertion order (which is chronological)
    # No need to reverse, dictionary keys maintain insertion order in Python 3.7+
    chat_ids = list(st.session_state.chats.keys())

    # Use st.container to manage layout and potential scrolling if list gets long
    history_container = st.container(height=300) # Example fixed height, adjust as needed
    with history_container:
        for chat_id in reversed(chat_ids): # Iterate reversed to show newest first
             if chat_id not in st.session_state.chats: continue # Skip if deleted during iteration

             chat_info = st.session_state.chats[chat_id]
             title = chat_info.get('title', "New Chat") # Use .get for safety
             # Update title dynamically if needed (only if no messages yet)
             if title == "New Chat" and chat_info['messages']:
                 st.session_state.chats[chat_id]['title'] = get_chat_title(chat_info['messages'])
                 title = st.session_state.chats[chat_id]['title']

             is_current = chat_id == st.session_state.current_chat_id

             # Use columns for title button and delete button
             col1, col2 = st.columns([5, 1])

             with col1:
                 if st.button(f"{title}", key=f"select_{chat_id}", use_container_width=True, type="primary" if is_current else "secondary", help=f"Switch to chat: {title}"):
                     if not is_current:
                         st.session_state.current_chat_id = chat_id
                         st.session_state.stop_streaming = False
                         st.session_state.is_generating = False
                         st.session_state.uploaded_file_content = None # Clear pending file on switch
                         st.session_state.uploaded_file_name = None
                         st.rerun()
             with col2:
                if st.button("🗑️", key=f"delete_{chat_id}", help="Delete this chat", use_container_width=True):
                     if len(st.session_state.chats) <= 1:
                          st.warning("Cannot delete the last chat.")
                     else:
                          # Find the next chat to select if we delete the current one
                          current_index = -1
                          ids_list = list(st.session_state.chats.keys()) # Get current order
                          try:
                               current_index = ids_list.index(chat_id)
                          except ValueError: pass # Should not happen

                          next_chat_id_to_select = None
                          if chat_id == st.session_state.current_chat_id:
                                if current_index > 0: # Try selecting the one before it in the list
                                     next_chat_id_to_select = ids_list[current_index - 1]
                                elif current_index < len(ids_list) - 1: # Try selecting the one after it
                                     next_chat_id_to_select = ids_list[current_index + 1]
                                # If it's the only one (and somehow delete was clicked), next_chat_id remains None


                          # Set delete request state for processing at top of script
                          st.session_state.delete_request = {"delete_id": chat_id, "next_id": next_chat_id_to_select}
                          st.rerun() # Rerun to process the deletion

    # --- Usage Info Section (Conditional) ---
    st.divider()
    current_chat_messages = st.session_state.chats.get(st.session_state.current_chat_id, {}).get("messages", [])

    # Context Usage (Conditional Display)
    if st.session_state.show_context_usage:
        current_context_tokens = sum(calculate_tokens(msg["content"]) for msg in current_chat_messages)
        context_usage_percent = (current_context_tokens / CONTEXT_WINDOW_SIZE) * 100
        st.caption(f"Context Usage (Approx):")
        st.progress(min(context_usage_percent / 100.0, 1.0))
        st.caption(f"{current_context_tokens:,} / {CONTEXT_WINDOW_SIZE:,} tokens ({context_usage_percent:.1f}%)")
        st.divider() # Add divider if context is shown

    # Token/Cost Totals (Conditional Display)
    if st.session_state.show_token_cost:
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0

        for msg in current_chat_messages:
             provider = msg.get("llm_provider", "Unknown") # Get provider used for this message
             if msg["role"] == "user":
                 tokens = msg.get("input_tokens", calculate_tokens(msg["content"])) # Recalculate if missing
                 total_input_tokens += tokens
                 total_cost += msg.get("input_cost", calculate_cost(tokens, "input", provider))
             elif msg["role"] == "assistant":
                 tokens = msg.get("output_tokens", calculate_tokens(msg["content"])) # Recalculate if missing
                 total_output_tokens += tokens
                 total_cost += msg.get("output_cost", calculate_cost(tokens, "output", provider))

        st.caption("Current Chat Totals (Approx):")
        st.caption(f"Input Tokens: {total_input_tokens:,}")
        st.caption(f"Output Tokens: {total_output_tokens:,}")
        st.caption(f"Estimated Cost: ${total_cost:.6f}")
        # Display cost note only if Gemini was used at all in the chat
        if any(msg.get("llm_provider") == "Gemini Flash" for msg in current_chat_messages):
             st.caption("(Gemini Flash cost shown as $0)")
        st.divider()


# --- Main Chat Window ---
chat_container = st.container()

with chat_container:
    # Check if current_chat_id is valid before accessing messages
    if st.session_state.current_chat_id in st.session_state.chats:
        messages = st.session_state.chats[st.session_state.current_chat_id]["messages"]
        for msg in messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"], unsafe_allow_html=True)
                # Removed per-message token/cost display here
    else:
        st.warning("Selected chat not found. Please select another chat or start a new one.")
        # Optionally select the latest chat automatically
        if st.session_state.chats:
             st.session_state.current_chat_id = list(st.session_state.chats.keys())[-1]
             st.rerun()


# --- User Input Area (Bottom) ---

# Container for elements above the chat input
input_controls_container = st.container()
with input_controls_container:
    # File Uploader (now less prominent)
    uploaded_file = st.file_uploader(
        "Attach File",
        type=['txt', 'md', 'py', 'json', 'yaml', 'csv'],
        key=f"file_uploader_{st.session_state.current_chat_id}", # Reset uploader when chat changes
        help="Attach a text-based file (TXT, MD, PY, etc.). Content will be added to your next message.",
        label_visibility="collapsed", # Hide the label, use placeholder/button text implicitly
        on_change=None # We handle the file processing on prompt submit
    )
    if uploaded_file is not None:
        # Store content immediately if a new file is uploaded
        try:
            st.session_state.uploaded_file_content = uploaded_file.read().decode("utf-8")
            st.session_state.uploaded_file_name = uploaded_file.name
            st.info(f"✅ File '{uploaded_file.name}' ready to send with your next message.", icon="📄")
        except Exception as e:
            st.error(f"Error reading file: {e}")
            st.session_state.uploaded_file_content = None
            st.session_state.uploaded_file_name = None

    # Conditional Stop Button
    if st.session_state.is_generating:
        # Use columns to place button somewhat aligned, adjust ratio if needed
        # Or simply place it above the input
        stop_col, _ = st.columns([1, 5]) # Button takes less space
        with stop_col:
             if st.button("⏹️ Stop", key="stop_button_main_input", help="Stop generating the response"):
                 st.session_state.stop_streaming = True
                 # Don't set is_generating=False here, the loop's finally block will handle it
                 st.warning("Stopping generation...")
                 # No rerun here, let the stream loop break naturally

# Chat Input Box - Use a key that changes with chat to ensure it resets properly
prompt = st.chat_input(
    "Enter your message here...",
    key=f"chat_input_{st.session_state.current_chat_id}",
    disabled=st.session_state.is_generating # Disable input while generating
)

if prompt:
    if st.session_state.selected_llm == "None":
        st.error("Please select an available LLM from the sidebar before sending a message.")
    else:
        st.session_state.stop_streaming = False # Ensure stop flag is reset

        # --- Handle File Attachment (One-Time) ---
        file_info_str = ""
        if st.session_state.uploaded_file_content and st.session_state.uploaded_file_name:
            st.info(f"Embedding file '{st.session_state.uploaded_file_name}' into message.", icon="📎")
            file_content_str = st.session_state.uploaded_file_content
            file_info_str = f"[Attached File: {st.session_state.uploaded_file_name}]\n```\n{file_content_str}\n```\n[End of File: {st.session_state.uploaded_file_name}]\n\n"
            # Clear the stored file content AFTER using it
            st.session_state.uploaded_file_content = None
            st.session_state.uploaded_file_name = None

        full_prompt = file_info_str + prompt
        # --- End File Handling ---

        # Append user message & calculate costs
        input_tokens = calculate_tokens(full_prompt)
        input_cost = calculate_cost(input_tokens, "input", st.session_state.selected_llm)
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
            # No per-message cost display here anymore

        # --- Call Selected LLM and Stream Response ---
        st.session_state.is_generating = True # Set generating flag
        st.rerun() # Rerun to show user message and potential stop button

# This block runs *after* the rerun triggered by setting is_generating = True
if st.session_state.is_generating and not prompt: # Check if we are in generating state but not due to a new prompt submit
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        response_stream = None
        assistant_message_content = "" # Store final content for state update

        try:
            # Prepare message history
            llm_messages = [{"role": m["role"], "content": m["content"]}
                            for m in st.session_state.chats[st.session_state.current_chat_id]["messages"]]

            # Check context window
            total_prompt_tokens = sum(calculate_tokens(m["content"]) for m in llm_messages)
            if total_prompt_tokens >= CONTEXT_WINDOW_SIZE:
                 st.error(f"Context window limit (~{CONTEXT_WINDOW_SIZE} tokens) approached. Please start a new chat.")
                 assistant_message_content = f"Error: Context window limit reached ({total_prompt_tokens}/{CONTEXT_WINDOW_SIZE} tokens)."

            else:
                # --- Dispatch to selected LLM ---
                current_llm = st.session_state.selected_llm
                client = available_llms_map.get(current_llm)

                if client and client.is_available():
                     response_stream = client.generate_completion(
                         messages=llm_messages,
                         stream=True
                         # Add other params like temperature if needed
                     )
                elif current_llm != "None":
                     st.error(f"{current_llm} client not available or not configured correctly.")
                     assistant_message_content = f"Error: Could not connect to {current_llm}."
                # else: case handled by initial prompt check

                # --- Stream Processing (Common Logic) ---
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
                         message_placeholder.markdown(assistant_message_content) # Update display with marker

                elif not assistant_message_content: # If stream failed and no error message set yet
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
             assistant_message_content = f"Sorry, an error occurred while generating the response using {st.session_state.selected_llm}."
             message_placeholder.error(assistant_message_content)
             # Log the full traceback for debugging if needed
             # import traceback
             # traceback.print_exc()
        finally:
            # --- Append assistant response (even if partial/error) ---
            if assistant_message_content: # Only append if there's some content (even error message)
                output_tokens = calculate_tokens(assistant_message_content)
                output_cost = calculate_cost(output_tokens, "output", st.session_state.selected_llm)
                assistant_message = {
                    "role": "assistant",
                    "content": assistant_message_content,
                    "output_tokens": output_tokens,
                    "output_cost": output_cost,
                    "llm_provider": st.session_state.selected_llm
                }
                st.session_state.chats[st.session_state.current_chat_id]["messages"].append(assistant_message)

                # Update chat title if it was the first proper exchange
                current_chat_messages = st.session_state.chats[st.session_state.current_chat_id]["messages"]
                if st.session_state.chats[st.session_state.current_chat_id]['title'] == "New Chat" and len(current_chat_messages) > 1: # Check length > 1
                     st.session_state.chats[st.session_state.current_chat_id]['title'] = get_chat_title(current_chat_messages)

            # --- Reset states and rerun ---
            st.session_state.is_generating = False
            st.session_state.stop_streaming = False # Ensure stop flag is reset here too
            st.rerun() # Rerun to update sidebar totals, title, remove stop button etc.

# --- End of App ---