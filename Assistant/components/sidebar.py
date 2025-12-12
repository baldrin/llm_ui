import streamlit as st
from datetime import datetime
import json

from config.constants import DEFAULT_CHAT_TITLE
from config.constants import CONTEXT_WINDOW_SIZE
from config.config_loader import config
from utils.core.id_generator import generate_chat_id
from utils.core.session_utils import cleanup_chat_cache
from utils.caching.cache_utils import get_cached_tokens
from utils.chat.context_manager import context_manager

from utils.content.file_handler import (
        process_uploaded_file,
        get_pdf_page_count
    )

from utils.core.structured_logger import (
    get_logger, 
    log_user_action
)

logger = get_logger(__name__)

def switch_to_chat(chat_id: str) -> None:
    """
    Switch to a different chat conversation with immediate UI response.
    """
    import time
    start_time = time.time()
    
    try:
        if chat_id != st.session_state.current_chat_id:
            try:
                st.session_state.current_chat_id = chat_id
                st.session_state.is_generating = False
                
                # Clear file attachments when switching chats
                if "pending_attachments" in st.session_state:
                    del st.session_state.pending_attachments
                
                switch_duration = (time.time() - start_time) * 1000
                
                log_user_action(
                    "switch_chat",
                    user_id=st.session_state.user_info.get("user_id"),
                    chat_id=chat_id,
                    duration_ms=switch_duration
                )
                
            except Exception as e:
                logger.error(
                    "chat_switch_failed",
                    chat_id=chat_id,
                    error=str(e)
                )
                st.error("Failed to switch conversations. Please refresh the page.")
                raise
            
    except Exception as e:
        logger.error(
            "chat_switch_error",
            chat_id=chat_id,
            error=str(e)
        )
        st.error(f"Failed to switch conversation: {str(e)}")


def create_new_chat() -> None:
    """Create a new chat conversation with error handling."""
    try:
        new_chat_id = generate_chat_id()
        new_chat_data = {
            "title": DEFAULT_CHAT_TITLE, 
            "messages": [],
            "created_at": None,
            "updated_at": None,
            "message_count": 0,
            "loaded_at": None
        }
        
        new_chats_dict = {new_chat_id: new_chat_data}
        new_chats_dict.update(st.session_state.chats)
        
        try:
            st.session_state.chats = new_chats_dict
            st.session_state.current_chat_id = new_chat_id
            st.session_state.is_generating = False
            
            # Clear file attachments when creating new chat
            if "pending_attachments" in st.session_state:
                del st.session_state.pending_attachments
            
            logger.info(
                "new_chat_created",
                chat_id=new_chat_id
            )
            st.toast("New conversation created!", icon="✨")
        except Exception as e:
            logger.error(
                "session_state_update_failed",
                error=str(e)
            )
            st.error("Failed to create new conversation. Please refresh the page.")
            raise
        
    except Exception as e:
        logger.error(
            "chat_creation_failed",
            error=str(e)
        )
        st.error(f"Failed to create new conversation: {str(e)}")


def delete_chat_callback(chat_id: str) -> None:
    """Delete a chat conversation with validation and error handling."""
    try:
        if len(st.session_state.chats) <= 1:
            st.toast("Cannot delete the last chat.", icon="⚠️")
            logger.warning(
                "delete_blocked_last_chat",
                chat_id=chat_id,
                total_chats=len(st.session_state.chats)
            )
            return
        
        if chat_id not in st.session_state.chats:
            st.toast("Chat not found.", icon="⚠️")
            logger.warning("delete_blocked_chat_not_found", chat_id=chat_id)
            return
        
        try:
            cleanup_chat_cache(chat_id)
            
            st.session_state.pending_delete_chat_id = chat_id
            st.session_state.needs_rerun = True
            
            logger.info(
                "chat_deletion_queued",
                chat_id=chat_id,
                user_id=st.session_state.user_info.get("user_id")
            )
            
        except Exception as e:
            logger.error(
                "deletion_queue_failed",
                error=str(e),
                chat_id=chat_id,
                error_type=type(e).__name__
            )
            st.error("Failed to queue chat deletion. Please try again.")
            raise
        
    except Exception as e:
        logger.error(
            "delete_callback_failed",
            error=str(e),
            chat_id=chat_id,
            error_type=type(e).__name__
        )
        st.error(f"Failed to delete conversation: {str(e)}")


def render_llm_selector(available_llms_map) -> None:
    """Render the LLM model selector."""
    available_llms_list = list(available_llms_map.keys())
    display_llms_list = available_llms_list
    current_selection = st.session_state.get('selected_llm', None)
    
    if current_selection not in available_llms_list:
        if available_llms_list:
            current_selection = available_llms_list[0]
            st.session_state.selected_llm = current_selection
        else:
            st.error(
                "No LLM clients are configured or available. "
                "Please check config.toml"
            )
            return
    
    try:
        selected_llm_index = display_llms_list.index(current_selection)
    except ValueError:
        selected_llm_index = 0

    selected_llm = st.selectbox(
        "Select Language Model", 
        options=display_llms_list, 
        index=selected_llm_index,
        key="llm_selector",
        help="Choose the language model to interact with."
    )
    
    if selected_llm != st.session_state.get('selected_llm'):
        st.session_state.selected_llm = selected_llm
    
    if not available_llms_list:
        st.error(
            "No LLM clients are configured or available. "
            "Please check config.toml"
        )


def render_file_uploader() -> None:
    """Render a compact file uploader in the sidebar with size AND token validation."""
    current_chat_id = st.session_state.get('current_chat_id')
    is_generating = st.session_state.get('is_generating', False)

    # Generate unique key with counter for forced resets
    key_counter = st.session_state.get('file_uploader_key_counter', 0)
    uploader_key = f"sidebar_file_uploader_{current_chat_id}_{key_counter}"

    # Get current conversation state for validation
    chat = st.session_state.chats.get(current_chat_id, {})
    messages = chat.get('messages', [])
    current_tokens = context_manager.get_current_tokens(messages)

    # Calculate remaining capacity
    remaining_tokens = CONTEXT_WINDOW_SIZE - current_tokens
    max_attachment_tokens = config.get('app.max_attachment_tokens', 20000)
    available_attachment_tokens = min(remaining_tokens, max_attachment_tokens)

    uploaded_files = st.file_uploader(
        "Attach images, PDFs, or text files",
        accept_multiple_files=True,
        disabled=is_generating,
        key=uploader_key,
        label_visibility="hidden"
    )

    if uploaded_files:
        if "pending_attachments" not in st.session_state:
            st.session_state.pending_attachments = {
                'text_files': [],
                'images': [],
                'pdfs': []
            }
        else:
            st.session_state.pending_attachments = {
                'text_files': [],
                'images': [],
                'pdfs': []
            }

        processed_files = []
        total_payload_size = 0
        total_estimated_tokens = 0

        max_payload_size = config.get('app.max_payload_size_mb', 3.5) * 1024 * 1024

        for uploaded_file in uploaded_files:
            try:
                file_type, text_content, image, pdf_bytes = process_uploaded_file(uploaded_file)

                # Calculate payload size AND tokens for this file
                payload_size = 0
                estimated_tokens = 0

                if file_type == 'text':
                    payload_size = len(text_content.encode('utf-8'))
                    estimated_tokens = len(text_content) // 3.5

                elif file_type == 'image':
                    from utils.content.image_encoder import estimate_image_size
                    size_info = estimate_image_size(image)
                    payload_size = int(size_info['payload_size_bytes'])
                    if 'estimated_tokens' in size_info:
                        estimated_tokens = size_info['estimated_tokens']
                    else:
                        width = size_info.get('width', 0)
                        height = size_info.get('height', 0)
                        estimated_tokens = (width * height) // 750 if width and height else 0

                elif file_type == 'pdf':
                    from utils.content.pdf_handler import pdf_handler

                    page_count = get_pdf_page_count(pdf_bytes)
                    max_pdf_pages = config.get('app.max_pdf_pages', 100)

                    if page_count > max_pdf_pages:
                        st.error(
                            f"❌ **{uploaded_file.name}**: Too many pages ({page_count}). "
                            f"Maximum allowed: {max_pdf_pages} pages"
                        )
                        logger.warning(
                            "pdf_rejected_too_many_pages",
                            filename=uploaded_file.name,
                            page_count=page_count,
                            max_pages=max_pdf_pages
                        )
                        continue

                    metadata = pdf_handler.estimate_pdf_metadata(pdf_bytes)
                    payload_size = metadata['payload_size_bytes']
                    estimated_tokens = page_count * 800

                # Check payload size limit (CRITICAL - API will reject)
                if total_payload_size + payload_size > max_payload_size:
                    max_mb = max_payload_size / (1024 * 1024)
                    st.error(
                        f"❌ **{uploaded_file.name}**: File too large.\n\n"
                        f"This file would exceed the **{max_mb:.1f}MB** upload limit."
                    )
                    logger.warning(
                        "file_rejected_payload_size_limit",
                        filename=uploaded_file.name,
                        file_payload_mb=payload_size / (1024*1024),
                        current_total_mb=total_payload_size / (1024*1024),
                        max_payload_mb=max_mb
                    )
                    continue

                # Check against available context capacity
                new_total_tokens = total_estimated_tokens + estimated_tokens

                if new_total_tokens > available_attachment_tokens:
                    # Calculate what percentage of remaining context this would use
                    context_percent = (new_total_tokens / remaining_tokens * 100) if remaining_tokens > 0 else 100

                    st.error(
                        f"❌ **{uploaded_file.name}**: Would exceed context capacity.\n\n"
                        #f"This conversation has **{current_tokens:,}** tokens used. "
                        #f"This file would add **{estimated_tokens:,}** tokens, exceeding available space.\n\n"
                        f"**Options:**\n"
                        f"- Start a new conversation\n"
                        f"- Use smaller/fewer attachments"
                    )
                    logger.warning(
                        "file_rejected_context_capacity",
                        filename=uploaded_file.name,
                        file_tokens=estimated_tokens,
                        current_tokens=current_tokens,
                        remaining_tokens=remaining_tokens,
                        available_attachment_tokens=available_attachment_tokens
                    )
                    continue

                # Check attachment token limit (prevents huge files)
                token_percent = (new_total_tokens / max_attachment_tokens) * 100

                if token_percent > 100:
                    st.error(
                        f"❌ **{uploaded_file.name}**: Too much content.\n\n"
                        f"This file contains too much content to attach. Try a file with less content, or fewer attachments."
                    )
                    logger.warning(
                        "file_rejected_token_limit",
                        filename=uploaded_file.name,
                        file_tokens=estimated_tokens,
                        current_total_tokens=total_estimated_tokens,
                        max_attachment_tokens=max_attachment_tokens,
                        token_percent=token_percent
                    )
                    continue

                total_payload_size += payload_size
                total_estimated_tokens += estimated_tokens

                if file_type == 'text':
                    st.session_state.pending_attachments['text_files'].append({
                        'name': uploaded_file.name,
                        'content': text_content
                    })
                    processed_files.append(uploaded_file.name)

                elif file_type == 'image':
                    st.session_state.pending_attachments['images'].append({
                        'name': uploaded_file.name,
                        'image': image
                    })
                    processed_files.append(uploaded_file.name)

                elif file_type == 'pdf':
                    st.session_state.pending_attachments['pdfs'].append({
                        'name': uploaded_file.name,
                        'bytes': pdf_bytes,
                        'pages': page_count
                    })
                    processed_files.append(uploaded_file.name)

                else:
                    st.error(f"❌ **{uploaded_file.name}**: Unsupported file type or unreadable")

            except Exception as e:
                st.error(f"❌ **{uploaded_file.name}**: {str(e)}")
                logger.error("file_processing_error", filename=uploaded_file.name, error=str(e))

        # Show status with context awareness
        if processed_files:
            max_mb = max_payload_size / (1024 * 1024)
            size_mb = total_payload_size / (1024 * 1024)
            token_percent = (total_estimated_tokens / max_attachment_tokens) * 100

            # Show context impact
            projected_total = current_tokens + total_estimated_tokens
            context_percent = (projected_total / CONTEXT_WINDOW_SIZE) * 100

            if context_percent >= 90:
                status_msg = f"**{len(processed_files)} file(s) attached** - Will use {context_percent:.0f}% of context"
                display_func = st.warning
            elif token_percent >= 90:
                status_msg = "**Exceeds content limit** - reduce attachments"
                display_func = st.error
            elif token_percent >= 75:
                status_msg = "**Approaching content limit**"
                display_func = st.warning
            else:
                status_msg = f"**{len(processed_files)} file(s) attached**"
                display_func = st.info

            display_func(status_msg)

            logger.debug(
                "files_attached",
                count=len(processed_files),
                payload_size_mb=size_mb,
                estimated_tokens=total_estimated_tokens,
                token_percent=token_percent,
                current_tokens=current_tokens,
                projected_total=projected_total,
                context_percent=context_percent
            )

    else:
        if "pending_attachments" in st.session_state:
            del st.session_state.pending_attachments


def render_chat_list() -> None:
    """Render chat conversation list - only showing chats that exist."""
    
    # CSS to hide container outline/border
    st.markdown("""
        <style>
        /* Hide container border - try multiple selectors */
        div[data-testid="stVerticalBlock"] > div > div[style*="overflow"] {
            border: none !important;
            outline: none !important;
        }
        
        /* Target the scrollable element directly */
        div[style*="overflow: auto"] {
            border: none !important;
            outline: none !important;
        }
        
        div[style*="overflow: scroll"] {
            border: none !important;
            outline: none !important;
        }
        
        /* Remove all borders from containers in sidebar */
        [data-testid="stSidebar"] div[style*="overflow"] {
            border: none !important;
            outline: none !important;
            box-shadow: none !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    with st.container(height=520, border=False):
        chat_ids = list(st.session_state.chats.keys())
        
        for chat_id in chat_ids:
            if chat_id not in st.session_state.chats:
                continue

            chat_info = st.session_state.chats[chat_id]
            title = chat_info.get("title", DEFAULT_CHAT_TITLE)
            is_current = chat_id == st.session_state.current_chat_id

            col1, col2 = st.columns([5, 1])

            with col1:
                st.button(
                    f"{title}", 
                    key=f"select_{chat_id}", 
                    use_container_width=True, 
                    type="primary" if is_current else "secondary",
                    on_click=switch_to_chat,
                    args=(chat_id,)
                )

            with col2:
                st.button(
                    "🗑️", 
                    key=f"delete_{chat_id}", 
                    help="Delete this chat", 
                    use_container_width=True,
                    on_click=delete_chat_callback,
                    args=(chat_id,)
                )

def render_sidebar() -> None:
    """Render the complete sidebar interface."""
    
    with st.sidebar:
        # CSS to align buttons vertically
        st.markdown(
            """
            <style>
            [data-testid="stSidebar"] {
                width: 390px !important;
            }

            /* Align column contents to center vertically */
            [data-testid="stHorizontalBlock"] > div {{
                display: flex !important;
                align-items: center !important;
            }}
            
            /* Remove extra padding from button containers */
            [data-testid="stVerticalBlock"]:has(button) {{
                padding-top: 0 !important;
                padding-bottom: 0 !important;
            }}
            
            /* Ensure buttons have same height and alignment */
            [data-testid="stHorizontalBlock"] button {{
                margin-top: 0 !important;
                margin-bottom: 0 !important;
            }}
            </style>
            """,
            unsafe_allow_html=True
        )

        if config.get('features.model_selection', False):
            available_llms_map = config.get('llm.llm_models', {})
            render_llm_selector(available_llms_map)
            st.divider()

        col1, col2 = st.columns(2)

        with col1:
            st.button(
                f"➕ {DEFAULT_CHAT_TITLE}", 
                use_container_width=True,
                help="Start a new conversation",
                on_click=create_new_chat
            )

        with col2:
            render_stop_button()
        
        render_compact_context_bar()

        if config.get('features.file_attachments', False):
            render_file_uploader()
        
        st.header("Chat History")

        with st.container():
            render_chat_list()

        if config.get('debug.show_sidebar_debug', False) and st.checkbox(
            "Show Debug Info",
            value=False
        ):
            render_sidebar_debug()            

def render_sidebar_debug() -> None:
    from services.db_connection_manager import get_db_manager
    from utils.monitoring.performance_monitor import performance_monitor
    from utils.monitoring.system_monitor import system_monitor

    st.divider() 

    st.subheader("🖥️ System Resources")
    

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Current Process**")
        process_stats = system_monitor.get_process_stats()

        # Color-code based on usage
        cpu_color = "🟢" if process_stats.get('cpu_percent', 0) < 50 else "🟡" if process_stats.get('cpu_percent', 0) < 80 else "🔴"
        mem_color = "🟢" if process_stats.get('memory_percent', 0) < 50 else "🟡" if process_stats.get('memory_percent', 0) < 80 else "🔴"

        st.metric(
            f"{cpu_color} CPU Usage",
            f"{process_stats.get('cpu_percent', 0)}%"
        )
        st.metric(
            f"{mem_color} Memory Usage",
            f"{process_stats.get('memory_mb', 0)} MB",
            f"{process_stats.get('memory_percent', 0)}%"
        )
        st.caption(f"Threads: {process_stats.get('threads', 0)} | PID: {process_stats.get('pid', 'N/A')}")

    with col2:
        st.markdown("**System Overall**")
        system_stats = system_monitor.get_system_stats()

        cpu_data = system_stats.get('cpu', {})
        mem_data = system_stats.get('memory', {})

        sys_cpu_color = "🟢" if cpu_data.get('overall_percent', 0) < 50 else "🟡" if cpu_data.get('overall_percent', 0) < 80 else "🔴"
        sys_mem_color = "🟢" if mem_data.get('percent', 0) < 50 else "🟡" if mem_data.get('percent', 0) < 80 else "🔴"

        st.metric(
            f"{sys_cpu_color} System CPU",
            f"{cpu_data.get('overall_percent', 0)}%"
        )
        st.metric(
            f"{sys_mem_color} System Memory",
            f"{mem_data.get('used_gb', 0):.1f} GB",
            f"{mem_data.get('percent', 0)}%"
        )
        st.caption(f"Total: {mem_data.get('total_gb', 0):.1f} GB | Available: {mem_data.get('available_gb', 0):.1f} GB")

    # CPU per core (if multiple cores)
    if cpu_data.get('per_core'):
        with st.expander("📊 CPU Per Core"):
            cores = cpu_data.get('per_core', [])
            for i, usage in enumerate(cores):
                color = "🟢" if usage < 50 else "🟡" if usage < 80 else "🔴"
                st.progress(usage / 100, text=f"{color} Core {i}: {usage}%")

    st.subheader("💾 Cache Statistics")
    cache_stats = system_monitor.get_cache_stats()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Image Metadata",
            cache_stats.get('image_metadata', {}).get('entries', 0)
        )

    with col2:
        base64_data = cache_stats.get('image_base64', {})
        st.metric(
            "Image Base64",
            base64_data.get('entries', 0),
            f"{base64_data.get('size_mb', 0)} MB"
        )

    with col3:
        st.metric(
            "PDF Metadata",
            cache_stats.get('pdf_metadata', {}).get('entries', 0)
        )

    with st.expander("🔝 Top 5 Processes by Memory"):
        top_procs = system_monitor.get_top_processes(limit=5)
        for proc in top_procs:
            if 'error' not in proc:
                st.text(f"{proc['name'][:20]:20} | PID: {proc['pid']:6} | MEM: {proc['memory_percent']:5.1f}% | CPU: {proc['cpu_percent']:5.1f}%")

    st.divider()

    st.subheader("Database Status")
    db_manager = get_db_manager()
    stats = db_manager.get_stats()
    st.json(stats)

    st.subheader("Chat Service Stats")
    chat_stats = st.session_state.chat_service.get_stats()
    st.json(chat_stats)

    st.subheader("Logging Stats")
    logger_stats = st.session_state.db_logger.get_stats()
    st.json(logger_stats)

    st.subheader("Performance Metrics")
    perf_stats = performance_monitor.get_stats()
    st.json(perf_stats)

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Reset Perform Stats"):
            performance_monitor.reset_stats()
            st.success("Stats reset!")
            st.session_state.needs_rerun = True
            #st.rerun()

    with col2:
        if st.button("Clear Caches"):
            if 'image_base64_cache' in st.session_state:
                del st.session_state.image_base64_cache
            if 'image_metadata_cache' in st.session_state:
                del st.session_state.image_metadata_cache
            if 'pdf_metadata_cache' in st.session_state:
                del st.session_state.pdf_metadata_cache
            st.success("Caches cleared!")
            st.session_state.needs_rerun = True
            #st.rerun()

    with col3:
        if st.button("Refresh Stats"):
            st.session_state.needs_rerun = True
            #st.rerun()

    st.subheader("Current Session")
    st.json({
        "current_chat_id": st.session_state.get("current_chat_id", "None"),
        "total_chats": len(st.session_state.get("chats", {})),
        "selected_llm": st.session_state.get("selected_llm", "None"),
        "is_generating": st.session_state.get("is_generating", False)
    })

    st.subheader("Environment Info")
    st.json(config.get_environment_info())

    st.divider()
    st.subheader("📋 Export Debug Info")

    # Collect all debug data
    debug_data = {
        "timestamp": datetime.now().isoformat(),
        "system_resources": {
            "process": system_monitor.get_process_stats(),
            "system": system_monitor.get_system_stats(),
            "top_processes": system_monitor.get_top_processes(limit=5)
        },
        "cache_stats": system_monitor.get_cache_stats(),
        "database": get_db_manager().get_stats(),
        "chat_service": st.session_state.chat_service.get_stats(),
        "logging": st.session_state.db_logger.get_stats(),
        "performance": performance_monitor.get_stats(),
        "session": {
            "current_chat_id": st.session_state.get("current_chat_id", "None"),
            "total_chats": len(st.session_state.get("chats", {})),
            "selected_llm": st.session_state.get("selected_llm", "None"),
            "is_generating": st.session_state.get("is_generating", False)
        },
        "environment": config.get_environment_info()
    }

    # Convert to formatted JSON string
    debug_json = json.dumps(debug_data, indent=2, default=str)

    # Create text area with the data (read-only)
    st.text_area(
        "Debug Data (JSON)",
        value=debug_json,
        height=200,
        key="debug_data_display",
        help="Copy this data to share debug information"
    )

    # Copy button using Streamlit's built-in clipboard
    if st.button("📋 Copy All Debug Info", use_container_width=True):
        st.code(debug_json, language="json")
        st.success("✅ Debug info displayed above - use your browser's copy function!")



def render_compact_context_bar() -> None:
    """Render a compact context bar below the chat input."""
    
    current_chat_id = st.session_state.get('current_chat_id')
    
    if not current_chat_id or current_chat_id not in st.session_state.chats:
        return
    
    chat = st.session_state.chats[current_chat_id]
    messages = chat.get('messages')
    
    total_tokens, show_loading = get_cached_tokens(current_chat_id, messages)
    
    context_status = context_manager.get_context_status(total_tokens)
    
    loading_indicator = ""
    if show_loading:
        loading_indicator = ' <span style="font-size: 10px; color: #999;">⏳</span>'
    
    st.markdown(
        f"""
        <style>
        .compact-context-bar {{
            width: 100%;
            background-color: var(--secondary-background-color, #f0f2f6);
            border-radius: 4px;
            overflow: hidden;
            height: 8px;
            position: relative;
            margin-top: 8px;
            margin-bottom: 16px;
        }}
        [data-theme="dark"] .compact-context-bar {{
            background-color: #262730;
        }}
        .compact-context-fill {{
            height: 100%;
            background-color: {context_status.color};
            width: {min(context_status.percentage, 100):.1f}%;
            transition: width 0.3s ease, background-color 0.3s ease;
            border-radius: 4px;
        }}
        .compact-context-tooltip {{
            font-size: 11px;
            color: var(--text-color, #666);
            text-align: center;
            margin-top: 4px;
        }}
        [data-theme="dark"] .compact-context-tooltip {{
            color: #a6a6a6;
        }}
        </style>
        <div class="compact-context-bar">
            <div class="compact-context-fill"></div>
        </div>
        <div class="compact-context-tooltip">
            Context: {total_tokens:,} / {CONTEXT_WINDOW_SIZE:,} tokens ({min(context_status.percentage, 100):.1f}%){loading_indicator}
        </div>
        """,
        unsafe_allow_html=True
    )

def render_stop_button() -> None:
    """
    Render stop button for generation control.
    """
    is_generating = st.session_state.get("is_generating", False)
    
    if is_generating:
        if st.button(
            "🔴 STOP",
            key="stop_generation_sidebar",
            type="primary",
            use_container_width=True,
            help="Click to stop the current generation"
        ):
            logger.info(
                "stop_button_clicked",
                current_partial=st.session_state.get("_streaming_partial_response", "")[:50],
                session_id=st.session_state.get("session_id")
            )
            
            st.session_state.stop_streaming = True
            st.session_state.save_partial_on_stop = True
            
            logger.info(
                "generation_stop_requested",
                stop_streaming=True,
                save_partial_on_stop=True
            )
            
            st.toast("⏹️ Stopping generation...", icon="⏳")
    else:
        st.button(
            "⚪ Stop Generation",
            key="stop_generation_sidebar_disabled",
            type="secondary",
            disabled=True,
            use_container_width=True,
            help="No active generation"
        )