import streamlit as st

def show_conversation_skeleton(num_messages: int = 3):
    """
    Display a skeleton loader for conversation messages.
    
    Args:
        num_messages: Number of skeleton message bubbles to show
    """
    st.markdown("""
        <style>
        .skeleton {
            animation: skeleton-loading 1s linear infinite alternate;
            background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
            background-size: 200% 100%;
            border-radius: 8px;
        }
        
        @keyframes skeleton-loading {
            0% {
                background-position: 200% 0;
            }
            100% {
                background-position: -200% 0;
            }
        }
        
        .skeleton-message {
            padding: 16px;
            margin: 12px 0;
            border-radius: 12px;
            background: white;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        
        .skeleton-line {
            height: 12px;
            margin: 8px 0;
            border-radius: 4px;
        }
        
        .skeleton-avatar {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            margin-right: 12px;
            display: inline-block;
            vertical-align: middle;
        }
        
        /* Dark mode support */
        @media (prefers-color-scheme: dark) {
            .skeleton {
                background: linear-gradient(90deg, #2d2d2d 25%, #3d3d3d 50%, #2d2d2d 75%);
            }
            .skeleton-message {
                background: #1e1e1e;
                box-shadow: 0 1px 3px rgba(255,255,255,0.1);
            }
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Show skeleton messages
    for i in range(num_messages):
        role = "assistant" if i % 2 == 0 else "user"
        with st.chat_message(role):
            st.markdown("""
                <div class="skeleton-message">
                    <div class="skeleton skeleton-line" style="width: 80%;"></div>
                    <div class="skeleton skeleton-line" style="width: 95%;"></div>
                    <div class="skeleton skeleton-line" style="width: 70%;"></div>
                </div>
            """, unsafe_allow_html=True)


def show_loading_spinner(
    message: str = "Loading...",
    icon: str = "⏳"
) -> None:
    """
    Show a professional loading spinner with custom message.
    
    Args:
        message: Loading message to display
        icon: Emoji icon to show
    """
    st.markdown(f"""
        <style>
        .loading-container {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 40px 20px;
            text-align: center;
        }}
        
        .loading-icon {{
            font-size: 48px;
            animation: pulse 1.5s ease-in-out infinite;
            margin-bottom: 20px;
        }}
        
        .loading-text {{
            font-size: 18px;
            color: #666;
            font-weight: 500;
            margin-bottom: 10px;
        }}
        
        .loading-subtext {{
            font-size: 14px;
            color: #999;
        }}
        
        @keyframes pulse {{
            0%, 100% {{
                transform: scale(1);
                opacity: 1;
            }}
            50% {{
                transform: scale(1.1);
                opacity: 0.7;
            }}
        }}
        
        .loading-dots {{
            display: inline-block;
        }}
        
        .loading-dots span {{
            animation: blink 1.4s infinite;
            animation-fill-mode: both;
        }}
        
        .loading-dots span:nth-child(2) {{
            animation-delay: 0.2s;
        }}
        
        .loading-dots span:nth-child(3) {{
            animation-delay: 0.4s;
        }}
        
        @keyframes blink {{
            0%, 80%, 100% {{
                opacity: 0;
            }}
            40% {{
                opacity: 1;
            }}
        }}
        
        /* Dark mode */
        @media (prefers-color-scheme: dark) {{
            .loading-text {{
                color: #e0e0e0;
            }}
            .loading-subtext {{
                color: #a0a0a0;
            }}
        }}
        </style>
        
        <div class="loading-container">
            <div class="loading-icon">{icon}</div>
            <div class="loading-text">
                {message}<span class="loading-dots"><span>.</span><span>.</span><span>.</span></span>
            </div>
            <div class="loading-subtext">This should only take a moment</div>
        </div>
    """, unsafe_allow_html=True)


def show_chat_list_skeleton(num_items: int = 5):
    """
    Display a skeleton loader for the chat list in sidebar.
    
    Args:
        num_items: Number of skeleton chat items to show
    """
    st.markdown("""
        <style>
        .chat-skeleton-item {
            padding: 12px;
            margin: 8px 0;
            border-radius: 8px;
            background: white;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        }
        
        @media (prefers-color-scheme: dark) {
            .chat-skeleton-item {
                background: #2d2d2d;
            }
        }
        </style>
    """, unsafe_allow_html=True)
    
    for _ in range(num_items):
        st.markdown("""
            <div class="chat-skeleton-item">
                <div class="skeleton skeleton-line" style="width: 70%; height: 14px;"></div>
                <div class="skeleton skeleton-line" style="width: 40%; height: 10px; margin-top: 8px;"></div>
            </div>
        """, unsafe_allow_html=True)


class LoadingContext:
    """Context manager for showing loading states with automatic cleanup."""
    
    def __init__(
        self, 
        message: str = "Loading...",
        icon: str = "⏳",
        show_skeleton: bool = False,
        skeleton_type: str = "conversation",
        skeleton_count: int = 3
    ):
        self.message = message
        self.icon = icon
        self.show_skeleton = show_skeleton
        self.skeleton_type = skeleton_type
        self.skeleton_count = skeleton_count
        self.container = None
    
    def __enter__(self):
        """Show loading state."""
        self.container = st.empty()
        
        with self.container:
            if self.show_skeleton:
                if self.skeleton_type == "conversation":
                    show_conversation_skeleton(self.skeleton_count)
                elif self.skeleton_type == "chat_list":
                    show_chat_list_skeleton(self.skeleton_count)
            else:
                show_loading_spinner(self.message, self.icon)
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clear loading state."""
        if self.container:
            self.container.empty()
        return False
