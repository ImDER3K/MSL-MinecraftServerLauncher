import customtkinter as ctk

def apply_styles():
    # Set the general appearance mode (Dark, Light, System)
    ctk.set_appearance_mode("Dark")
    
    # Set the default color theme (blue, dark-blue, green)
    ctk.set_default_color_theme("blue")
    
    # We can also define standard sizes and fonts to use throughout the app here
    return {
        "fonts": {
            "heading": ("Roboto", 20, "bold"),
            "body": ("Roboto", 14),
            "console": ("Consolas", 12)
        },
        "colors": {
            "bg": "#242323",           # Main background
            "fg": "#454343",           # Foreground elements (frames)
            "primary": "#417A6D",      # Buttons, highlights
            "secondary": "#2F544C",    # Secondary highlights
            "text": "#ffffff",         # Main text
            "text_muted": "#8d99ae",   # Subdued text
            "danger": "#ef233c",       # Stop/Delete buttons
            "success": "#38b000"       # Start, Online status
        }
    }
