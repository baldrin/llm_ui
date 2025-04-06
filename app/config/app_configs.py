# Define configurations for different apps
APP_CONFIGS = {
    "assistant": {
        "title": "Developer Assistant",
        "icon": "💬",
        "description": "General-purpose AI assistant",
        "system_prompt": "You are a helpful assistant that provides accurate and thoughtful responses.",
        "features": {
            "file_upload": True,
            "code_highlighting": True,
            "token_counting": True,
            "model_selection": True
        }
    },
}

def get_app_config(app_id):
    """Get configuration for a specific app."""
    return APP_CONFIGS.get(app_id, APP_CONFIGS["assistant"])  # Default to assistant