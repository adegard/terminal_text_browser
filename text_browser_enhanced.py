#!/usr/bin/env python3
"""
TERMINAL TEXT BROWSER - ENHANCED UI VERSION (1.54)
Web browser in terminal with improved UI/UX

Original version: 1.53
Enhanced version: 1.54 with UI improvements
Branch: ui-improvements
"""
import os
import re
import shutil
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import (
    urljoin, urlparse, parse_qs, unquote,
    urlunparse
)
from PIL import Image
from io import BytesIO
import sys
import termios
import tty
import PyPDF2
import time
import hashlib

# ========= BASIC CONFIG =========
APP_VERSION = "1.54-enhanced"

SAFE_MODE = True
STRIP_DDG_TRACKING = True

DUCK_LITE = "https://lite.duckduckgo.com/lite/"
BOOKMARK_FILE = os.path.expanduser("~/.tbrowser_bookmarks")

SEARCH_ENGINES = {
    "duck_lite": "DuckDuckGo Lite",
    "duck_html": "DuckDuckGo HTML",
    "brave": "Brave Search",
    "google": "Google (text mode)",
    "bing": "Bing (text mode)"
}

# ========= COLORS =========
C_RESET = "\033[0m"
C_TITLE = "\033[96m"
C_LINK  = "\033[93m"
C_CMD   = "\033[92m"
C_ERR   = "\033[91m"
C_DIM   = "\033[90m"
C_TEXT  = "\033[0m"

# ========= NEW: UI HELPER FUNCTIONS =========

def draw_box(title="", content="", width=None):
    """
    Draw a bordered box with optional title and content
    
    Example:
        draw_box("Search Results")
        draw_box("Error", "Connection failed")
    """
    if width is None:
        width = shutil.get_terminal_size().columns - 4
    
    box_width = max(20, min(width, shutil.get_terminal_size().columns - 2))
    
    print(f"{C_DIM}┌{'─' * (box_width - 2)}┐{C_RESET}")
    if title:
        title_str = title[:box_width - 4]
        print(f"{C_TITLE}│ {title_str:<{box_width - 4}} │{C_RESET}")
        if content:
            print(f"{C_DIM}├{'─' * (box_width - 2)}┤{C_RESET}")
    if content:
        content_str = content[:box_width - 4]
        print(f"{C_TEXT}│ {content_str:<{box_width - 4}} │{C_RESET}")
    print(f"{C_DIM}└{'─' * (box_width - 2)}┘{C_RESET}")

def show_message(msg_type, title, content):
    """
    Display styled messages with icons and colors
    
    Types: 'error', 'success', 'warning', 'info'
    
    Example:
        show_message("error", "Failed", "Connection timeout")
        show_message("success", "Saved", "Bookmark saved")
    """
    icons = {"error": "❌", "success": "✅", "warning": "⚠️", "info": "ℹ️"}
    colors = {
        "error": C_ERR,
        "success": "\033[38;5;34m",
        "warning": "\033[38;5;226m",
        "info": C_TITLE
    }
    
    icon = icons.get(msg_type, "•")
    color = colors.get(msg_type, C_DIM)
    
    cols = shutil.get_terminal_size().columns
    print(f"\n{color}{'─' * cols}{C_RESET}")
    print(f"{color}{icon} {title}{C_RESET}")
    print(f"{color}{content}{C_RESET}")
    print(f"{color}{'─' * cols}{C_RESET}\n")

def progress_bar_enhanced(current, total, width=30):
    """
    Enhanced progress bar with color gradient
    Color changes from red → orange → yellow → green based on progress
    
    Example:
        pb = progress_bar_enhanced(5, 10)
        # Output: [▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░] 50%
    """
    if total <= 0:
        return "──────────────────────────────"
    
    ratio = current / total
    filled = int(ratio * width)
    empty = width - filled
    
    # Color gradient based on progress
    if ratio < 0.25:
        color = "\033[38;5;196m"  # Red
    elif ratio < 0.50:
        color = "\033[38;5;208m"  # Orange
    elif ratio < 0.75:
        color = "\033[38;5;226m"  # Yellow
    else:
        color = "\033[38;5;46m"   # Green
    
    bar = "▓" * filled + "░" * empty
    percent = int(ratio * 100)
    
    return f"{color}[{bar}] {percent}%{C_RESET}"

def draw_command_palette(commands):
    """
    Display commands in an organized palette
    
    Example:
        commands = ["↑/p=prev", "↓/n=next", "q=quit"]
        draw_command_palette(commands)
    """
    cols = shutil.get_terminal_size().columns
    palette = " │ ".join(commands)
    
    if len(palette) > cols - 4:
        # Split into multiple lines if too long
        for i in range(0, len(commands), 3):
            group = commands[i:i+3]
            print(f"{C_CMD}{' │ '.join(group)}{C_RESET}")
    else:
        print(f"{C_CMD}{palette}{C_RESET}")

def draw_page_header(title, page_num, total_pages, is_bookmarked=False):
    """
    Draw a clean header for page display
    
    Example:
        draw_page_header("Article Title", 3, 10, True)
    """
    cols = shutil.get_terminal_size().columns
    
    # Top border
    print(f"{C_DIM}{'─' * cols}{C_RESET}")
    
    # Title with bookmark indicator
    bm_icon = "📌 " if is_bookmarked else "   "
    title_display = f"{bm_icon}{title}"[:cols-1]
    print(f"{C_TITLE}{title_display}{C_RESET}")
    
    # Metadata line (centered)
    meta = f"Page {page_num}/{total_pages}"
    padding = (cols - len(meta)) // 2
    print(f"{C_DIM}{' ' * padding}{meta}{C_RESET}")
    
    # Bottom border
    print(f"{C_DIM}{'─' * cols}{C_RESET}")
    print()

def clear_screen():
    """Clear terminal screen"""
    os.system("clear")

def main():
    """Demo of new UI functions"""
    clear_screen()
    print(f"{C_TITLE}Terminal Text Browser - Enhanced UI Version{C_RESET}")
    print(f"{C_DIM}Version 1.54-enhanced{C_RESET}\n")
    
    # Demo: Draw box
    print(f"{C_CMD}Demo 1: Styled Box{C_RESET}")
    draw_box("Welcome", "Enhanced Terminal Browser")
    print()
    
    # Demo: Show message
    print(f"{C_CMD}Demo 2: Styled Messages{C_RESET}")
    show_message("success", "Setup Complete", "All components loaded successfully")
    
    # Demo: Progress bar
    print(f"{C_CMD}Demo 3: Enhanced Progress Bar{C_RESET}")
    for i in range(0, 11):
        pb = progress_bar_enhanced(i, 10)
        print(f"Progress: {pb}")
        time.sleep(0.1)
    print()
    
    # Demo: Page header
    print(f"{C_CMD}Demo 4: Page Header{C_RESET}")
    draw_page_header("Sample Article Title", 3, 10, True)
    
    # Demo: Command palette
    print(f"{C_CMD}Demo 5: Command Palette{C_RESET}")
    commands = ["Space/↓=next", "p/↑=prev", "l=links", "m=bookmark", "h=home", "q=quit"]
    draw_command_palette(commands)
    print()
    
    print(f"{C_DIM}This is a demonstration of the new UI functions.{C_RESET}")
    print(f"{C_LINK}For full browser functionality, run: python text_browser.py{C_RESET}\n")
    
    input("Press ENTER to exit...")

if __name__ == "__main__":
    main()
