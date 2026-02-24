#!/usr/bin/env python3
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


# ========= BASIC CONFIG =========
APP_VERSION = "1.0"

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

# ========= PERSISTENT CONFIG =========
CONFIG_FILE = os.path.expanduser("~/.tbrowser_config.json")

DEFAULT_CONFIG = {
    "PARAS_PER_PAGE": 2,
    "DEFAULT_ENGINE": "duck_lite",
    "SEARCH_RESULTS_PER_PAGE": 10,
    "groq_api_key": "",
    "COLOR_THEME": "default",
    "CHRONOLOGY_LENGTH": 5,
    "MAX_CHARS_PER_BLOCK": 2000,
    "SHOW_READING_MENUS": True,
    "SHOW_PAGE_TITLE": True,
    "SHOW_PROGESS_BAR": True,
    "ADAPTIVE_WPM_PDF": 70,
    "ADAPTIVE_WPM_HTML": 70
}


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
    except Exception:
        return DEFAULT_CONFIG.copy()

    cfg = DEFAULT_CONFIG.copy()
    for k in DEFAULT_CONFIG:
        if k in data:
            cfg[k] = data[k]
    return cfg

def save_config():
    cfg = {
        "PARAS_PER_PAGE": PARAS_PER_PAGE,
        "DEFAULT_ENGINE": DEFAULT_ENGINE,
        "SEARCH_RESULTS_PER_PAGE": SEARCH_RESULTS_PER_PAGE,
        "groq_api_key": GROQ_API_KEY,
        "COLOR_THEME": COLOR_THEME,
        "CHRONOLOGY_LENGTH": CHRONOLOGY_LENGTH,
        "MAX_CHARS_PER_BLOCK": MAX_CHARS_PER_BLOCK,
        "SHOW_READING_MENUS": SHOW_READING_MENUS,
        "SHOW_PAGE_TITLE": SHOW_PAGE_TITLE,
        "SHOW_PROGESS_BAR": SHOW_PROGESS_BAR,
        "ADAPTIVE_WPM_PDF": ADAPTIVE_WPM_PDF,
        "ADAPTIVE_WPM_HTML": ADAPTIVE_WPM_HTML
    }

    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

# load config into globals
_cfg = load_config()
PARAS_PER_PAGE = _cfg["PARAS_PER_PAGE"]
DEFAULT_ENGINE = _cfg["DEFAULT_ENGINE"]
SEARCH_RESULTS_PER_PAGE = _cfg["SEARCH_RESULTS_PER_PAGE"]
COLOR_THEME = _cfg.get("COLOR_THEME", "default")
MAX_CHARS_PER_BLOCK = _cfg.get("MAX_CHARS_PER_BLOCK", 2000)
GROQ_API_KEY = _cfg.get("groq_api_key", "")
CHRONOLOGY_LENGTH = _cfg.get("CHRONOLOGY_LENGTH", 5)
SHOW_READING_MENUS = _cfg.get("SHOW_READING_MENUS", True)
SHOW_PAGE_TITLE = _cfg.get("SHOW_PAGE_TITLE", True)
SHOW_PROGESS_BAR = _cfg.get("SHOW_PROGESS_BAR", True)
ADAPTIVE_WPM_PDF = _cfg.get("ADAPTIVE_WPM_PDF", 70)
ADAPTIVE_WPM_HTML = _cfg.get("ADAPTIVE_WPM_HTML", 70)



# ========= COLORS =========
def apply_color_theme():
    global C_RESET, C_TITLE, C_LINK, C_CMD, C_ERR, C_DIM, C_TEXT

    theme = COLOR_THEME

    # --- Automatic mode ---
    if theme == "automatic":
        from datetime import datetime
        hour = datetime.now().hour
        # Night from 18:00 to 06:00
        if hour >= 20 or hour < 6:
            theme = "night"
        else:
            theme = "default"

    if theme == "night":
        C_RESET = "\033[0m"
        C_TITLE = "\033[38;5;250m"
        C_LINK  = "\033[38;5;180m"
        C_CMD   = "\033[38;5;65m"
        C_ERR   = "\033[38;5;131m"
        C_DIM   = "\033[38;5;240m"
        C_TEXT  = "\033[38;5;245m"
    else:
        C_RESET = "\033[0m"
        C_TITLE = "\033[96m"
        C_LINK  = "\033[93m"
        C_CMD   = "\033[92m"
        C_ERR   = "\033[91m"
        C_DIM   = "\033[90m"
        C_TEXT  = "\033[0m"


apply_color_theme()


# ========= HTTP SESSION =========
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

# ========= CLEANING + WRAPPING =========
def show_ai_answer(answer):
    # Normalize
    if isinstance(answer, list):
        answer = "\n\n".join(str(x) for x in answer)
    answer = answer.strip()

    paragraphs = answer.split("\n\n")
    page = 0

    while True:
        clear_screen()
        print(f"{C_TITLE}=== AI ANSWER ==={C_RESET}\n")
        print(paragraphs[page])
        print(f"\n{C_DIM}Paragraph {page+1}/{len(paragraphs)}{C_RESET}")
        print(f"{C_CMD}↑/p=prev  ↓/ENTER=next  q=quit{C_RESET}")

        key = read_key()

        if key in ("q", "Q"):
            return
        if key in ("UP", "p") and page > 0:
            page -= 1
            continue
        if key in ("DOWN", "\n", " "):
            if page < len(paragraphs) - 1:
                page += 1
                continue
            return



def clean_paragraph(text):
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def wrap(text, width):
    words = text.split()
    lines = []
    current = ""

    for w in words:
        if len(current) + len(w) + (1 if current else 0) > width:
            if current:
                lines.append(current)
            current = w
        else:
            current = w if current == "" else current + " " + w

    if current:
        lines.append(current)

    return lines

# ========= BOOKMARKS =========
HISTORY_FILE = os.path.expanduser("~/.tbrowser_history")

def load_history():
    # Create empty file if missing
    if not os.path.exists(HISTORY_FILE):
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        with open(HISTORY_FILE, "w") as f:
            pass
        return []

    items = []
    with open(HISTORY_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("|||")
            if len(parts) == 2:
                title, url = parts
                items.append((title, url))
    return items


def save_history(items):
    # Ensure directory exists
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)

    # Create file if missing and write cleanly
    with open(HISTORY_FILE, "w") as f:
        for title, url in items:
            safe_title = title if title else ""
            f.write(f"{safe_title}|||{url}\n")


def add_history(title, url):
    hist = load_history()
    # remove duplicates
    hist = [(t, u) for (t, u) in hist if u != url]
    # prepend newest
    hist.insert(0, (title if title else "", url))
    # trim
    hist = hist[:CHRONOLOGY_LENGTH]
    save_history(hist)


def load_bookmarks():
    if not os.path.exists(BOOKMARK_FILE):
        return []

    bookmarks = []
    with open(BOOKMARK_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            parts = line.split("|||")

            if len(parts) == 3:
                # NEW FORMAT: title|||url|||block
                title, url, block = parts
                try:
                    block = int(block)
                except:
                    block = 0
                bookmarks.append((title if title else None, url, block))

            elif len(parts) == 2:
                # OLD FORMAT: url|||block
                url, block = parts
                try:
                    block = int(block)
                except:
                    block = 0
                bookmarks.append((None, url, block))

            elif len(parts) == 1:
                # VERY OLD FORMAT: url only
                url = parts[0]
                bookmarks.append((None, url, 0))

            else:
                # Corrupted line — skip safely
                continue

    return bookmarks
    
def save_bookmark(url, block_index, title=None):
    bookmarks = load_bookmarks()
    updated = False

    for i, (t, u, b) in enumerate(bookmarks):
        if u == url:
            bookmarks[i] = (title if title else t, url, block_index)
            updated = True
            break

    if not updated:
        bookmarks.append((title, url, block_index))

    with open(BOOKMARK_FILE, "w") as f:
        for t, u, b in bookmarks:
            safe_title = t if t else ""
            f.write(f"{safe_title}|||{u}|||{b}\n")

def delete_bookmark_by_url(url):
    bookmarks = load_bookmarks()
    new_list = [(t, u, b) for (t, u, b) in bookmarks if u != url]

    with open(BOOKMARK_FILE, "w") as f:
        for t, u, b in new_list:
            safe_title = t if t else ""
            f.write(f"{safe_title}|||{u}|||{b}\n")

def delete_bookmark(i):
    b = load_bookmarks()
    if 0 <= i < len(b):
        del b[i]
        with open(BOOKMARK_FILE, "w") as f:
            for title, url, block in b:
                safe_title = title if title else ""
                f.write(f"{safe_title}|||{url}|||{block}\n")

def read_key():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)

        # Arrow keys start with ESC
        if ch == "\x1b":
            seq = sys.stdin.read(2)  # read the next two chars
            if seq == "[A":
                return "UP"
            if seq == "[B":
                return "DOWN"
            if seq == "[C":
                return "RIGHT"
            if seq == "[D":
                return "LEFT"
            return ch  # unknown escape sequence

        # Backspace normalization
        if ch == "\x7f":
            return "BACKSPACE"

        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

# ========= USEFULL HELPERS =========

def get_remote_version():
    url = "https://raw.githubusercontent.com/adegard/terminal_text_browser/refs/heads/main/version.txt"
    try:
        r = session.get(url, timeout=10)
        r.raise_for_status()
        return r.text.strip()
    except Exception:
        return None

def download_latest_script():
    url = "https://raw.githubusercontent.com/adegard/terminal_text_browser/refs/heads/main/text_browser.py"
    try:
        r = session.get(url, timeout=10)
        r.raise_for_status()
        return r.text
    except Exception:
        return None


def auto_update():
    clear_screen()
    print(f"{C_TITLE}=== AUTO UPDATE ==={C_RESET}\n")
    print(f"Current version: {APP_VERSION}")

    remote = get_remote_version()
    if not remote:
        print(f"{C_ERR}Could not fetch remote version.{C_RESET}")
        input("\nPress ENTER…")
        return

    print(f"Latest version:  {remote}")

    if remote == APP_VERSION:
        print(f"\n{C_CMD}You are already up to date.{C_RESET}")
        input("\nPress ENTER…")
        return

    print(f"\n{C_ERR}New version available!{C_RESET}")
    print("Downloading…")

    new_script = download_latest_script()
    if not new_script:
        print(f"{C_ERR}Failed to download new script.{C_RESET}")
        input("\nPress ENTER…")
        return

    current_file = os.path.abspath(sys.argv[0])
    backup_file = current_file + ".backup"

    try:
        shutil.copy2(current_file, backup_file)

        with open(current_file, "w") as f:
            f.write(new_script)

        print(f"\n{C_CMD}Update complete!{C_RESET}")
        print(f"Backup saved as: {backup_file}")
        print("\nRestart the browser to use the new version.")
    except Exception as e:
        print(f"{C_ERR}Update failed: {e}{C_RESET}")

    input("\nPress ENTER…")



def resolve_redirect(url):
    try:
        r = session.head(url, allow_redirects=True, timeout=10)
        return r.url
    except Exception:
        return url


# def update_adaptive_wpm(current_wpm, words, seconds):
#    if seconds <= 0:
#        return current_wpm

#    measured = (words / seconds) * 60
#    alpha = 0.2  # smoothing factor
#
#    return (1 - alpha) * current_wpm + alpha * measured


def estimate_reading_time(paragraphs, current_block, wpm=70):
    # if wpm is None:
    #    wpm = ADAPTIVE_WPM

    total_blocks = len(paragraphs)

    # If we are on the LAST block → remaining time is zero
    if current_block >= total_blocks - 1:
        return "0 sec"

    # Otherwise count remaining blocks normally
    remaining_text = " ".join(paragraphs[current_block+1:])
    words = len(remaining_text.split())
    minutes = words / wpm

    if words == 0:
        return "0 sec"

    if minutes < 1:
        seconds = int(minutes * 60)
        return f"{seconds} sec"

    if minutes > 60:
        hours = minutes / 60
        return f"{hours:.1f} hours"

    return f"{minutes:.1f} min"


def extract_pdf_text(url):
    try:
        r = session.get(url, timeout=20)
        r.raise_for_status()
    except Exception as e:
        return [f"[PDF fetch error: {e}]"]

    try:
        reader = PyPDF2.PdfReader(BytesIO(r.content))
    except Exception as e:
        return [f"[PDF parse error: {e}]"]
        
    # Extract title 
    pdf_title = extract_pdf_title(reader)

    paragraphs = []
    for page in reader.pages:
        text = page.extract_text() or ""
        text = clean_paragraph(text)
        if text.strip():
            paragraphs.append(text)

    if not paragraphs:
        return ["[PDF contains no extractable text]"]

    return paragraphs, pdf_title

def extract_pdf_title(reader):
    """
    Extract the PDF title from metadata if available.
    Falls back to None if missing or unreadable.
    """
    try:
        info = reader.metadata
        if info and info.title:
            title = str(info.title).strip()
            if title:
                return title
    except Exception:
        pass
    return None


def normalize_url(t):
    t = t.strip()
    if t.startswith("http://") or t.startswith("https://"):
        return t
    if "." in t:
        return "https://" + t
    return None

def strip_duckduckgo_tracking(url):
    if not STRIP_DDG_TRACKING:
        return url
    p = urlparse(url)
    if "duckduckgo.com" not in p.netloc:
        return url
    return urlunparse(p._replace(query=""))

def unwrap_duckduckgo_redirect(url):
    if url.startswith("//duckduckgo.com/l/?"):
        url = "https:" + url
    p = urlparse(url)
    if "duckduckgo.com" in p.netloc and p.path.startswith("/l"):
        qs = parse_qs(p.query)
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
    return url

def unwrap_generic_redirect(url):
    return strip_duckduckgo_tracking(unwrap_duckduckgo_redirect(url))

def is_ad_or_tracker(url):
    if not SAFE_MODE:
        return False
    host = urlparse(url).netloc.lower()
    bad = ["doubleclick", "adservice", "adsystem", "tracking",
           "analytics", "pixel", "googlesyndication"]
    return any(b in host for b in bad)

# ========= FETCH & PARSE =========
def fetch(url):
    r = session.get(url, timeout=15, allow_redirects=True)
    r.raise_for_status()
    return r.text

def fetch_main_image_url(soup, base_url):
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return urljoin(base_url, og["content"])

    img = soup.find("img")
    if img and img.get("src"):
        return urljoin(base_url, img["src"])

    return None

def extract_title(soup):
    if soup.title and soup.title.string:
        return clean_paragraph(soup.title.string)
    return None


def extract_single_page(html, base):
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    # Wattpad / generic <pre> special case
    pre_blocks = soup.find_all("pre")
    if pre_blocks:
        paragraphs = []
        for pre in pre_blocks:
            ps = pre.find_all("p")
            if ps:
                for p in ps:
                    raw = p.get_text(" ", strip=True)
                    clean = clean_paragraph(raw)
                    if len(clean) > 5:
                        paragraphs.append(clean)
            else:
                raw = pre.get_text(" ", strip=True)
                clean = clean_paragraph(raw)
                if len(clean) > 20:
                    paragraphs.append(clean)

        links = []
        for a in soup.find_all("a", href=True):
            label = a.get_text(" ", strip=True)
            href = unwrap_generic_redirect(urljoin(base, a["href"]))
            if not is_ad_or_tracker(href):
                links.append((label if label else href, href))

        main_image = fetch_main_image_url(soup, base)
        title = extract_title(soup)
        return paragraphs, links, main_image, title

    candidates = []
    for tag in soup.find_all(["article", "main", "div"]):
        size = len(tag.get_text(strip=True))
        candidates.append((size, tag))
    candidates.sort(key=lambda x: x[0], reverse=True)
    main = candidates[0][1] if candidates else soup.body or soup

    paragraphs = []
    for p in main.find_all(["p", "li"]):
        raw = p.get_text(" ", strip=True)
        clean = clean_paragraph(raw)
        if len(clean) > 20:
            paragraphs.append(clean)

    links = []
    for a in main.find_all("a", href=True):
        label = a.get_text(" ", strip=True)
        href = unwrap_generic_redirect(urljoin(base, a["href"]))
        if not is_ad_or_tracker(href):
            links.append((label if label else href, href))

    main_image = fetch_main_image_url(soup, base)
    title = extract_title(soup)
    return paragraphs, links, main_image, title


def chunk_paragraphs(paragraphs, n):
    for i in range(0, len(paragraphs), n):
        yield paragraphs[i:i+n]

def paginate(items, n=20):
    for i in range(0, len(items), n):
        yield items[i:i+n]

# ========= SEARCH IMPLEMENTATIONS =========
def flatten_ai_output(content):
    # Recursively flatten nested lists until we get a string
    while isinstance(content, list) and len(content) == 1:
        content = content[0]

    # If it's still a list, join all elements
    if isinstance(content, list):
        return "\n\n".join(str(x) for x in content)

    # If it's not a string, convert it
    return str(content)


def ai_query(prompt):
    if not GROQ_API_KEY:
        return "AI ERROR:\nNo Groq API key set. Go to Settings → Set Groq API key."

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    data = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    try:
        r = session.post(url, headers=headers, json=data, timeout=20)
        r.raise_for_status()
        j = r.json()
        content = j["choices"][0]["message"]["content"]

        # --- FIX: flatten ANY nested structure ---
        content = flatten_ai_output(content)

        return content.strip()

    except Exception as e:
        return f"AI ERROR:\n{e}"


def search_duck(q):
    r = session.get(DUCK_LITE + "?q=" + q, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    results = []
    for a in soup.select("a.result-link"):
        title = a.get_text(" ", strip=True)
        href = unwrap_generic_redirect(a.get("href"))
        if not is_ad_or_tracker(href):
            results.append((title, href))
    return results

def search_duck_html(q):
    url = "https://duckduckgo.com/html/?q=" + q
    r = session.get(url, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    results = []
    for a in soup.select("a.result__a"):
        title = a.get_text(" ", strip=True)
        href = unwrap_generic_redirect(a.get("href"))
        if not is_ad_or_tracker(href):
            results.append((title, href))
    return results

def search_brave(q):
    url = "https://search.brave.com/search?q=" + q + "&source=web"
    r = session.get(url, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    results = []
    for a in soup.select("a.result-header"):
        title = a.get_text(" ", strip=True)
        href = unwrap_generic_redirect(a.get("href"))
        if not is_ad_or_tracker(href):
            results.append((title, href))
    return results

def search_google_text(q):
    try:
        url = "https://textise.net/showtext.aspx?strURL=https://www.google.com/search?q=" + q
        r = session.get(url, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        results = []
        for a in soup.find_all("a"):
            href = a.get("href")
            if not href:
                continue
            if "http" not in href:
                continue
            title = a.get_text(" ", strip=True)
            if title and not is_ad_or_tracker(href):
                results.append((title, href))

        if not results:
            return search_duck(q)

        return results

    except Exception:
        return search_duck(q)

def search_bing_text(q):
    url = "https://www.bing.com/search?q=" + q + "&form=MSNVS"
    r = session.get(url, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    results = []
    for li in soup.select("li.b_algo h2 a"):
        title = li.get_text(" ", strip=True)
        href = unwrap_generic_redirect(li.get("href"))
        if not is_ad_or_tracker(href):
            results.append((title, href))
    return results

def search(q):
    if DEFAULT_ENGINE == "duck_lite":
        return search_duck(q)     
    if DEFAULT_ENGINE == "duck_html":
        return search_duck_html(q)
    if DEFAULT_ENGINE == "brave":
        return search_brave(q)
    if DEFAULT_ENGINE == "google":
        return search_google_text(q)
    if DEFAULT_ENGINE == "bing":
        return search_bing_text(q)
    return search_duck(q)

def shorten_middle(text, max_len):
    if len(text) <= max_len:
        return text
    if max_len < 10:
        return text[:max_len]
    keep = (max_len - 3) // 2
    return text[:keep] + "..." + text[-keep:]

# ========= UI HELPERS =========
def clear_screen():
    os.system("clear")

def print_search_results_page(results_page, page_idx, total_pages):
    clear_screen()
    print(f"{C_TITLE}=== SEARCH RESULTS ==={C_RESET}\n")
    for i, (title, url) in enumerate(results_page, 1):
        print(f"{C_LINK}{i}. {C_RESET}{title}")
        cols = shutil.get_terminal_size().columns
        short_url = shorten_middle(url, cols - 6)
        print(f"{C_TITLE}URL: {short_url}{C_RESET}")
    print()
    print(f"{C_DIM}Page {page_idx+1}/{total_pages}{C_RESET}")
    print(f"{C_CMD}number=open  [ENTER]=next  p=prev  bm=bookmarks  h=home  q=quit{C_RESET}")

# ========= SETTINGS MENU =========
def settings_menu():
    global PARAS_PER_PAGE, DEFAULT_ENGINE, SEARCH_RESULTS_PER_PAGE, COLOR_THEME, MAX_CHARS_PER_BLOCK, GROQ_API_KEY
    global CHRONOLOGY_LENGTH, SHOW_READING_MENUS, SHOW_PAGE_TITLE, SHOW_PROGESS_BAR, ADAPTIVE_WPM_PDF, ADAPTIVE_WPM_HTML
    
    while True:
        clear_screen()
        print(f"{C_TITLE}=== SETTINGS ==={C_RESET}\n")
        print(f"1. Paragraphs per page: {PARAS_PER_PAGE}")
        print(f"2. Search engine: {SEARCH_ENGINES[DEFAULT_ENGINE]}")
        print(f"3. Search results per page: {SEARCH_RESULTS_PER_PAGE}")
        print(f"4. Color theme: {COLOR_THEME}")
        print(f"5. Set Groq API key (please allow model llama-3.1-8b-instant) (current: {'SET' if GROQ_API_KEY else 'NOT SET'})")
        print(f"6. Chronology length: {CHRONOLOGY_LENGTH}")
        print(f"7. Max characters per block: {MAX_CHARS_PER_BLOCK}")
        print(f"8. Show menus in reading: {SHOW_READING_MENUS}")
        print(f"9. Show page title page: {SHOW_PAGE_TITLE}")
        print(f"10. Show progress/remaining: {SHOW_PROGESS_BAR}")
        print(f"11. Words per Min (PDF): {ADAPTIVE_WPM_PDF}")
        print(f"12. Words per Min (HTML): {ADAPTIVE_WPM_HTML}")
        print(f"13. Check for updates")
        print("\nq = back\n")

        c = input("> ").strip().lower()

        if c == "q":
            return

        if c == "1":
            val = input("Paragraphs per page (1–20): ").strip()
            if val.isdigit() and 1 <= int(val) <= 20:
                PARAS_PER_PAGE = int(val)
                save_config()
            continue

        if c == "2":
            clear_screen()
            print(f"{C_TITLE}=== SEARCH ENGINES ==={C_RESET}\n")
            keys = list(SEARCH_ENGINES.keys())
            for i, key in enumerate(keys, 1):
                print(f"{i}. {SEARCH_ENGINES[key]}")
            print("\nq = back\n")

            s = input("> ").strip().lower()
            if s == "q":
                continue
            if s.isdigit():
                idx = int(s) - 1
                if 0 <= idx < len(keys):
                    DEFAULT_ENGINE = keys[idx]
                    save_config()
            continue

        if c == "3":
            val = input("Search results per page (5–50): ").strip()
            if val.isdigit() and 5 <= int(val) <= 50:
                SEARCH_RESULTS_PER_PAGE = int(val)
                save_config()
            continue

        if c == "4":
            print("\n1. default")
            print("2. night")
            print("3. automatic (8pm-6am)")
            s = input("> ").strip()
            if s == "1":
                COLOR_THEME = "default"
            elif s == "2":
                COLOR_THEME = "night"
            elif s == "3":
                COLOR_THEME = "automatic"
            else:
                continue

            apply_color_theme()
            save_config()

            continue

        if c == "5":
            print("\nEnter your Groq API key:")
            key = input("> ").strip()
            if key:
                GROQ_API_KEY = key
                save_config()
                print("Groq API key saved.")
                input("Enter…")
            continue
        if c == "6": 
            val = input("Chronology length (1–200): ").strip() 
            if val.isdigit() and 1 <= int(val) <= 200: 
                CHRONOLOGY_LENGTH = int(val) 
                save_config() 
            continue

        if c == "7":
            val = input("Max characters per block (200–5000): ").strip()
            if val.isdigit() and 200 <= int(val) <= 5000:
                MAX_CHARS_PER_BLOCK = int(val)
                save_config()
            continue

        if c == "8":
            SHOW_READING_MENUS = not SHOW_READING_MENUS
            save_config()
            continue

        if c == "9":
            SHOW_PAGE_TITLE = not SHOW_PAGE_TITLE
            save_config()
            continue

        if c == "10":
            SHOW_PROGESS_BAR = not SHOW_PROGESS_BAR
            save_config()
            continue

        if c == "11":
            val = input("Words per min for PDF(60–300): ").strip()
            if val.isdigit() and 60 <= int(val) <= 300:
                ADAPTIVE_WPM_PDF = int(val)
                save_config()
            continue

        if c == "12":
            val = input("Words per min for HTML pages (60–300): ").strip()
            if val.isdigit() and 60 <= int(val) <= 300:
                ADAPTIVE_WPM_HTML = int(val)
                save_config()
            continue

        if c == "13":
            clear_screen()
            auto_update()
            continue

# ========= HOME =========
def home():
    while True:
        clear_screen()
        print(r"""
           _.-''''''-._
        .-'  _     _   '-.
      .'    (_)   (_)     '.
     /      .-'''-.         \
    |     .'       `.        |
    |    /  .---.    \       |
    |    |  /   \ |   |      |
     \   \  \___/ /   /     /
      '.  '._   _.'  .'     /
        '-._'''''_.-'     .'
             '-.....-'
        """)
        print(f"\n{C_TITLE}=== TEXT BROWSER ==={C_RESET}")
        print(f"{C_DIM}(Search text / ifl + text=I'm feeling lucky / Url / bm=bookmarks / c=chronology / s=settings / ai + text=ask AI / q=quit){C_RESET}")

        t = input("> ").strip()
        if not t:
            continue

        low = t.lower()

        # Instant First Link search: ifl <query>
        if low.startswith("ifl "):
            q = t[4:].strip()
            if not q:
                print("Usage: ifl <search terms>")
                continue

            results = search(q)
            if not results:
                print(f"{C_ERR}No results.{C_RESET}")
                input("Enter…")
                continue

            # Open the first result immediately
            title, url = results[0]
            return ("open_url", url, "search", 0)

        # AI mode: ai <question>
        if t.startswith("ai "):
            question = t[3:].strip()
            if not question:
                print("Write: ai your question")
                continue

            if not GROQ_API_KEY:
                print("\nNo Groq API key found.")
                print("Go to Settings → Set Groq API key.")
                continue
            print(f"\n{C_TITLE}=== AI ANSWER ==={C_RESET}\n")
            answer = ai_query(question)
            show_ai_answer(answer)
            continue

        if low == "q":
            return ("quit",)

        if low == "bm":
            return ("bookmarks",)

        if low == "s":
            settings_menu()
            continue

        if low == "c":
            return ("chronology",)

        url = normalize_url(t)
        if url:
            return ("open_url", url, "direct")

        return ("search", t)

# ========= SEARCH RESULTS LOOP =========
def search_and_select(query):
    results = search(query)
    if not results:
        print(f"{C_ERR}No results.{C_RESET}")
        input("Enter…")
        return None

    pages = list(paginate(results, SEARCH_RESULTS_PER_PAGE))
    page_idx = 0

    while True:
        current_page = pages[page_idx]
        print_search_results_page(current_page, page_idx, len(pages))
        raw = input("Result> ")
        c = raw.strip().lower()

        if raw == "":
            c = "next"

        if c == "q":
            return ("quit",)

        if c == "h":
            return None

        if c == "bm":
            bm = bookmark_manager()
            if bm:
                title, url, block = bm
                return ("url", url, "bm", block)
            continue

        if c == "c": 
            cm = chronology_manager() 
            if cm: 
                _, title, url = cm 
                return ("url", url, "chronology", 0) 
            continue
        
        if c == "next" and page_idx < len(pages) - 1:
            page_idx += 1
            continue

        if c == "p" and page_idx > 0:
            page_idx -= 1
            continue

        if c.isdigit():
            i = int(c)
            if 1 <= i <= len(current_page):
                return ("url", current_page[i-1][1], "search", 0)

        input(f"{C_ERR}Invalid.{C_RESET} Enter…")

def handle_nav(nav):
    while True:
        if nav is None:
            return None

        kind = nav[0]

        # QUIT
        if kind == "quit":
            return ("quit",)

        # HOME
        if kind == "home":
            return ("home",)

        # BACK
        if kind == "back":
            origin = nav[1]
            if origin == "search":
                return ("search_again",)
            if origin == "bm":
                return ("open_bookmarks",)
            if origin == "chronology":
                return ("open_chronology",)
            return ("home",)

        # OPEN BOOKMARK
        if kind == "open_bm":
            _, title, url, block = nav
            nav = show_page(url, "bm", block)
            continue

        # OPEN CHRONOLOGY
        if kind == "open_chronology":
            _, title, url = nav
            nav = show_page(url, "chronology", 0)
            continue

        # OPEN URL
        if kind == "open_url":
            _, url, origin, block = nav
            url = resolve_redirect(url)
            nav = show_page(url, origin, block)
            continue

        # Unknown → home
        return ("home",)
        
# ========= BOOKMARK CHECKER =========


def is_bookmarked(url):
    for title, u, block in load_bookmarks():
        if u == url:
            return True
    return False

def get_bookmark_block(url):
    for title, u, block in load_bookmarks():
        if u == url:
            return block
    return None

# ========= BOOKMARK MANAGER =========

def bookmark_manager():
    while True:
        clear_screen()
        b = load_bookmarks()
        print(f"{C_TITLE}=== BOOKMARKS ==={C_RESET}\n")

        if not b:
            print("No bookmarks.")
            input("\nEnter…")
            return None

        for i, (title, url, block) in enumerate(b, 1):
            label = title if title else url
            cols = shutil.get_terminal_size().columns
            short_url = shorten_middle(url, max(20, cols - len(label) - 20))

            print(f"{i}. {label}")
            print(f"   {C_DIM}{short_url}  [block {block}]{C_RESET}")

        print(f"\n{C_CMD}number=open  d#=delete  q=back{C_RESET}")

        c = input("> ").strip().lower()

        if c == "q":
            return None
        if c.startswith("d") and c[1:].isdigit():
            delete_bookmark(int(c[1:]) - 1)
            continue
        if c.isdigit():
            i = int(c) - 1
            if 0 <= i < len(b):
                title, url, block = b[i]
                return (title, url, block)

def chronology_manager():
    while True:
        clear_screen()
        h = load_history()
        print(f"{C_TITLE}=== CHRONOLOGY ==={C_RESET}\n")

        if not h:
            print("No history.")
            input("\nEnter…")
            return None

        for i, (title, url) in enumerate(h, 1):
            label = title if title else url
            cols = shutil.get_terminal_size().columns
            short_url = shorten_middle(url, max(20, cols - len(label) - 20))
            print(f"{i}. {label}")
            print(f"   {C_DIM}{short_url}{C_RESET}")

        print(f"\n{C_CMD}number=open  q=back{C_RESET}")

        c = input("> ").strip().lower()

        if c == "q":
            return None

        if c.isdigit():
            i = int(c) - 1
            if 0 <= i < len(h):
                title, url = h[i]
                return ("chronology", title, url)

        
# ========= PAGE VIEW =========
def build_text_pages(paragraphs):
    if not paragraphs:
        return [["[No readable text]"]]

    # --- NEW: split paragraphs exceeding MAX_CHARS_PER_BLOCK ---
    processed = []
    for para in paragraphs:
        if len(para) <= MAX_CHARS_PER_BLOCK:
            processed.append(para)
        else:
            # split into chunks
            for i in range(0, len(para), MAX_CHARS_PER_BLOCK):
                processed.append(para[i:i+MAX_CHARS_PER_BLOCK])

    # Now paginate normally
    pages = []
    for block in chunk_paragraphs(processed, PARAS_PER_PAGE):
        lines = []
        cols = shutil.get_terminal_size().columns
        usable_width = max(10, cols)
        for para in block:
            clean = clean_paragraph(para)
            wrapped = wrap(clean, usable_width)
            lines.extend(wrapped)
            lines.append("")
        pages.append(lines)

    return pages


def render_image_halfblocks(img, max_width):
    img = img.convert("RGB")
    new_width = max_width
    new_height = int((img.height / img.width) * new_width * 0.5)
    img = img.resize((new_width, new_height * 2))

    pixels = img.load()
    lines = []

    for y in range(0, img.height, 2):
        line = ""
        for x in range(img.width):
            top = pixels[x, y]
            bottom = pixels[x, y+1] if y+1 < img.height else top
            line += (
                f"\033[38;2;{top[0]};{top[1]};{top[2]}m"
                f"\033[48;2;{bottom[0]};{bottom[1]};{bottom[2]}m▀"
            )
        line += "\033[0m"
        lines.append(line)

    return lines

def show_image_in_terminal(url):
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content))
    except Exception as e:
        return [f"[Image error: {e}]"]

    cols = shutil.get_terminal_size().columns
    max_width = max(20, cols - 2)
    return render_image_halfblocks(img, max_width)

def try_load_next_part(url, paragraphs):
    # Detect current page number
    m = re.search(r"/page/(\d+)", url)
    if m:
        current_page = int(m.group(1))
        base = url[:url.rfind("/page/")]
    else:
        current_page = 1
        base = url.rstrip("/")

    next_page = current_page + 1
    next_url = f"{base}/page/{next_page}"

    try:
        html = fetch(next_url)
    except Exception:
        return None  # no next page

    # extract full metadata (4 values)
    new_pars, links, main_image, title = extract_single_page(html, next_url)

    if not new_pars:
        return None  # no content

    # Deduplicate
    existing = set(paragraphs)
    added = [p for p in new_pars if p not in existing]

    if not added:
        return None  # no new content

    # Append new paragraphs
    paragraphs.extend(added)

    # ALWAYS return 5 values
    return paragraphs, links, main_image, title, next_url

def progress_bar(current, total, width=20):
    """
    Render a simple terminal progress bar.
    Example: [██████░░░░░░░░] 42%
    """
    if total <= 0:
        return "----------"

    ratio = current / total
    filled = int(ratio * width)
    empty = width - filled

    # bar = "█" * filled + "░" * empty
    # bar = "•" * filled + "·" * empty
    # bar = "▮" * filled + "▯" * empty
    bar = "─" * filled + "" + "+" * (empty-1) + ""

    percent = int(ratio * 100)

    #return f"[{bar}] {percent}%"
    return f"{bar}"

def show_page(url, origin, start_block=0):
    global ADAPTIVE_WPM_HTML, ADAPTIVE_WPM_PDF
    is_pdf = False
    
    url = resolve_redirect(url)

    # >>> FIXED: unified fetch + PDF detection
    try:
        if url.lower().endswith(".pdf"):
            # PDF mode
            paragraphs, pdf_title = extract_pdf_text(url)
            links = []
            main_image = None
            is_pdf = True
            page_title = pdf_title if pdf_title else "PDF Document"
        else:
            # Normal HTML mode
            html = fetch(url)
            paragraphs, links, main_image, page_title = extract_single_page(html, url)

    except Exception as e:
        print(f"{C_ERR}{e}{C_RESET}")
        input("Enter…")
        return ("home",)
    # <<< END FIX

    # paragraphs, links, main_image, page_title = extract_single_page(html, url)
    text_pages = build_text_pages(paragraphs)
    link_pages = list(paginate(links, 5))

    # record visit
    add_history(page_title if page_title else url, url)

    mode = "text"
    page = start_block if 0 <= start_block < len(text_pages) else 0
    

    # start time
    block_start_time = time.time()

    while True:
        clear_screen()
        cols = shutil.get_terminal_size().columns

        # ---------------- TEXT MODE ----------------
        if mode == "text":
            if page >= len(text_pages):
                page = len(text_pages) - 1
            if page < 0:
                page = 0

            # progress bar instead of block count
            pb = progress_bar(page + 1, len(text_pages))

            #f"{C_DIM}Block {page+1}/{len(text_pages)}{C_RESET} " #old block showing numbers
                                           
            if SHOW_PROGESS_BAR:
                # --- Progess Bar & Remaining reading time ---
                if is_pdf:
                    wpm = ADAPTIVE_WPM_PDF
                else:
                    wpm = ADAPTIVE_WPM_HTML

                remaining = estimate_reading_time(paragraphs, page, wpm=wpm)
                #remaining = estimate_reading_time(paragraphs, page)
                # print(f"{C_DIM}{pb}{remaining}{C_RESET}")
                print(f"{C_DIM}{pb} {page+1}/{len(text_pages)}{C_RESET}")
                
            for line in text_pages[page]:
                print(f"{C_TEXT}{line}{C_RESET}")
 

            if SHOW_READING_MENUS:
                print(f"{C_CMD}Space/↓=next  p/↑=prev  l=links  i=image  "
                    f"b=back  bc=chronology-back  m=save  s=share bm=bookmarks  h=home  q=quit{C_RESET}"
                )

        # ---------------- LINKS MODE ----------------
        else:
            if link_pages and 0 <= page < len(link_pages):
                for i, (label, link) in enumerate(link_pages[page], 1):
                    short_label = label[:60] + "…" if len(label) > 60 else label
                    short_link = shorten_middle(link, cols - len(short_label) - 10)
                    print(f"{i}. {short_label} {C_DIM}→ {short_link}{C_RESET}")
                print(f"\n{C_DIM}Page {page+1}/{len(link_pages)}{C_RESET}")
            else:
                print("[No links]\n")

            print(
                f"{C_CMD}[SPACE]=next  p=prev  number=open  "
                f"t=text  b=back  h=home  q=quit{C_RESET}"
            )

        # ---------------- TITLE & BOOKMARKED----------------
        # Bookmark indicator
        if is_bookmarked(url):
            bm_flag = "\033[38;5;34m✔\033[0m"       # darker green
        else:
            bm_flag = "" # "\033[38;5;124m✘ (m+Enter)\033[0m"  # darker red

        title_to_show = page_title if page_title else shorten_middle(url, cols - 6)
        
        if SHOW_PAGE_TITLE:
            print(f"{C_TEXT}{title_to_show}{bm_flag}{C_RESET}")
        else:
            print(f"{bm_flag}")
        print(" ", end="", flush=True)

        # ---------------- INPUT ----------------
        key = read_key()

        if key == "DOWN":
            c = "next"
        elif key == "UP":
            c = "p"
        elif key == " ":
            c = "next"
        elif key == "\n":
            c = "next"
        elif key == "BACKSPACE":
            print("\b \b", end="", flush=True)
            rest = input()
            c = rest.strip().lower()
        else:
            print(key, end="", flush=True)
            rest = input()
            c = (key + rest).strip().lower()

        # ---------------- GLOBAL COMMANDS ----------------
        if c == "q":
            return ("quit",)

        if c == "h":
            return ("home",)

        if c == "b":
            if origin == "search":
                return ("back", origin)

            if origin == "bm":
                return ("back", origin)

            if origin == "chronology":
                return ("back", origin)

            return ("home",)

        if c == "bc":
            hist = load_history()
            if len(hist) < 2:
                input("No previous page in chronology. Enter…")
                continue
            prev_title, prev_url = hist[1]
            return ("open_url", prev_url, "chronology", 0)

        if c == "m":
            save_bookmark(url, page, page_title)
            input("Saved. Enter…")
            continue
        if c == "bm":
            bm = bookmark_manager()
            if bm:
                title, bm_url, bm_block = bm
                return ("open_bm", title, bm_url, bm_block)
            continue
        # --- SHARE SHORTCUT: 's' ---
        
        if c == "s":
            clear_screen()
            print(f"{C_TITLE}=== SHARE LINK ==={C_RESET}\n")

            # Try to shorten the URL with TinyURL
            short_url = url
            try:
                r = session.get(
                    "https://tinyurl.com/api-create.php",
                    params={"url": url},
                    timeout=10
                )
                r.raise_for_status()
                su = r.text.strip()
                if su.startswith("http"):
                    short_url = su
            except Exception:
                pass  # fallback to original URL

            # Show both URLs
            print(f"{C_TITLE}Original URL:{C_RESET}")
            print(url)
            print()
            print(f"{C_TITLE}TinyURL:{C_RESET}")
            print(short_url)
            print()

            print(f"{C_DIM}Press ENTER to return to block {page+1}{C_RESET}")
            input()
            continue


        # ---------------- TEXT MODE LOGIC ----------------
        if mode == "text":
            if c == "l":
                mode = "links"
                page = 0
                continue

            if c == "next":
                if page < len(text_pages) - 1:
                    page += 1
                    
                    # >>> ADDED: Auto‑update bookmark 
                    if is_bookmarked(url): 
                        save_bookmark(url, page, page_title) 
                    # estimate time
                    # elapsed = time.time() - block_start_time
                    # words = len(paragraphs[page].split())
                    # if is_pdf:
                    #    ADAPTIVE_WPM_PDF = update_adaptive_wpm(ADAPTIVE_WPM_PDF, words, elapsed)
                    # else:
                    #    ADAPTIVE_WPM_HTML = update_adaptive_wpm(ADAPTIVE_WPM_HTML, words, elapsed)

                    # save_config()
                    continue

                # try next part
                result = try_load_next_part(url, paragraphs)
                if result:
                    old_url = url
                    paragraphs, links, main_image, page_title, url = result
                    text_pages = build_text_pages(paragraphs)
                    link_pages = list(paginate(links, 5))
                    # Delete bookmark oldest page:
                    delete_bookmark_by_url(old_url)
                    # Auto bookmark new page:
                    save_bookmark(url, page, page_title) 
                    continue

                input(f"{C_DIM}End of content.{C_RESET} Enter…")
                continue

            if c == "p" and page > 0:
                page -= 1
                continue

            if c == "i":
                if not main_image:
                    input(f"{C_ERR}No image found.{C_RESET} Enter…")
                    continue

                clear_screen()
                print(f"{C_TITLE}=== ARTICLE IMAGE ==={C_RESET}\n")
                img_lines = show_image_in_terminal(main_image)
                for line in img_lines:
                    print(line)
                print(f"\n{C_CMD}Enter=back{C_RESET}")
                input()
                continue

            # --- AI inside reading mode ---
            if c.startswith("ai"):
                # Extract question
                q = c[2:].strip()

                # If no question, use current block text
                if not q:
                    block_text = "\n".join(text_pages[page])
                    q = f"Explain this briefly:\n{block_text}"

                # Call AI
                answer = ai_query(q)

                # Reduce to 1 paragraph
                answer = clean_paragraph(answer)

                clear_screen()
                print(f"{C_TITLE}=== AI ANSWER ==={C_RESET}\n")
                print(answer)
                print(f"\n{C_DIM}Press ENTER to return to block {page+1}{C_RESET}")
                input()
                continue

        # ---------------- LINKS MODE LOGIC ----------------
        else:
            if c == "t":
                mode = "text"
                page = 0
                continue

            if c == "next" and page < len(link_pages) - 1:
                page += 1
                continue

            if c == "p" and page > 0:
                page -= 1
                continue

            # FIXED: return proper tuple for main loop
            if c.isdigit() and link_pages:
                i = int(c) - 1
                if 0 <= page < len(link_pages) and 0 <= i < len(link_pages[page]):
                    link = link_pages[page][i][1]
                    return ("open_url", link, "page", 0)

        input(f"{C_ERR}Invalid.{C_RESET} Enter…")

# ========= MAIN LOOP =========
def main():
    mode = "home"
    current_url = None
    origin = "direct"
    last_search_query = None
    start_block = 0

    while True:

        # ---------------- HOME MODE ----------------
        if mode == "home":
            action = home()

            if action[0] == "quit":
                clear_screen()
                break

            if action[0] == "bookmarks":
                mode = "bookmarks"
                continue

            if action[0] == "chronology":
                cm = chronology_manager()
                if cm:
                    _, title, url = cm
                    nav = show_page(url, "chronology", 0)

                    # chain open_url
                    while isinstance(nav, tuple) and nav[0] == "open_url":
                        _, url2, origin2, block2 = nav
                        nav = show_page(url2, origin2, block2)

                    if nav == ("quit",):
                        clear_screen()
                        break
                continue

            if action[0] == "open_url":
                current_url = action[1]
                origin = action[2]
                start_block = 0
                mode = "page"
                continue

            if action[0] == "search":
                last_search_query = action[1]
                mode = "search"
                continue

        # ---------------- SEARCH MODE ----------------
        elif mode == "search":
            res = search_and_select(last_search_query)

            if res is None:
                mode = "home"
                continue

            if res[0] == "quit":
                clear_screen()
                break

            if res[0] == "url":
                current_url = res[1]
                origin = res[2]
                start_block = res[3] if len(res) > 3 else 0
                mode = "page"
                continue

        # ---------------- BOOKMARKS MODE ----------------
        elif mode == "bookmarks":
            bm = bookmark_manager()

            if bm is None:
                mode = "home"
                continue

            title, current_url, start_block = bm
            origin = "bm"
            mode = "page"
            continue

        # ---------------- PAGE MODE ----------------
        elif mode == "page":
            nav = show_page(current_url, origin, start_block)

            # ---- unified navigation handling ----
            while isinstance(nav, tuple) and nav[0] == "open_url":
                _, url, origin, block = nav
                url = resolve_redirect(url)
                nav = show_page(url, origin, block)
                
            # QUIT
            if nav == ("quit",) or nav == "quit":
                clear_screen()
                break

            # HOME
            if nav == ("home",) or nav == "home":
                mode = "home"
                current_url = None
                origin = "direct"
                start_block = 0
                continue

            # BACK
            if isinstance(nav, tuple) and nav[0] == "back":
                back_origin = nav[1]
                if back_origin == "search":
                    mode = "search"
                elif back_origin == "bm":
                    mode = "bookmarks"
                elif back_origin == "chronology":
                    mode = "chronology"
                else:
                    mode = "home"
                continue

            # OPEN BOOKMARK
            if isinstance(nav, tuple) and nav[0] == "open_bm":
                _, title, current_url, start_block = nav
                origin = "bm"
                mode = "page"
                continue

            # OPEN CHRONOLOGY
            if isinstance(nav, tuple) and nav[0] == "open_chronology":
                _, title, current_url = nav
                origin = "chronology"
                start_block = 0
                mode = "page"
                continue

            # STRING URL (fallback)
            if isinstance(nav, str):
                current_url = nav
                start_block = 0
                continue

if __name__ == "__main__":
    main()
