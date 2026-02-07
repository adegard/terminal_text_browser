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


# ========= BASIC CONFIG =========
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
    "COLOR_THEME": "default",
    "MAX_CHARS_PER_BLOCK": 2000   
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
        "COLOR_THEME": COLOR_THEME,
        "MAX_CHARS_PER_BLOCK": MAX_CHARS_PER_BLOCK
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



# ========= COLORS =========
def apply_color_theme():
    global C_RESET, C_TITLE, C_LINK, C_CMD, C_ERR, C_DIM, C_TEXT

    if COLOR_THEME == "night":
        C_RESET = "\033[0m"
        C_TITLE = "\033[38;5;250m"
        C_LINK  = "\033[38;5;180m"
        C_CMD   = "\033[38;5;65m"
        C_ERR   = "\033[38;5;131m"
        C_DIM   = "\033[38;5;240m"
        C_TEXT  = "\033[38;5;245m"   # <— grey paragraph text
    else:
        C_RESET = "\033[0m"
        C_TITLE = "\033[96m"
        C_LINK  = "\033[93m"
        C_CMD   = "\033[92m"
        C_ERR   = "\033[91m"
        C_DIM   = "\033[90m"
        C_TEXT  = "\033[0m"         # default terminal text


apply_color_theme()


# ========= HTTP SESSION =========
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

# ========= CLEANING + WRAPPING =========
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

# ========= URL HELPERS =========

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
    r = session.get(url, timeout=15)
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
    global PARAS_PER_PAGE, DEFAULT_ENGINE, SEARCH_RESULTS_PER_PAGE, COLOR_THEME, MAX_CHARS_PER_BLOCK

    while True:
        clear_screen()
        print(f"{C_TITLE}=== SETTINGS ==={C_RESET}\n")
        print(f"1. Paragraphs per page: {PARAS_PER_PAGE}")
        print(f"2. Search engine: {SEARCH_ENGINES[DEFAULT_ENGINE]}")
        print(f"3. Search results per page: {SEARCH_RESULTS_PER_PAGE}")
        print(f"4. Color theme: {COLOR_THEME}")
        print(f"5. Max characters per block: {MAX_CHARS_PER_BLOCK}")
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
            clear_screen()
            print(f"{C_TITLE}=== COLOR THEMES ==={C_RESET}\n")
            print("1. default (bright)")
            print("2. night (dim grey, dark green)")
            print("\nq = back\n")

            s = input("> ").strip().lower()
            if s == "q":
                continue
            if s == "1":
                COLOR_THEME = "default"
                apply_color_theme()
                save_config()
            if s == "2":
                COLOR_THEME = "night"
                apply_color_theme()
                save_config()
            continue
        if c == "5":
            val = input("Max characters per block (200–5000): ").strip()
            if val.isdigit() and 200 <= int(val) <= 5000:
                MAX_CHARS_PER_BLOCK = int(val)
                save_config()
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
        print(f"\n{C_TITLE}=== TEXT BROWSER V.0 ==={C_RESET}")
        print(f"{C_DIM}(Search / Url / bm=bookmarks / s=settings / q=quit){C_RESET}")

        t = input("> ").strip()
        if not t:
            continue

        low = t.lower()

        if low == "q":
            return ("quit",)

        if low == "bm":
            return ("bookmarks",)

        if low == "s":
            settings_menu()
            continue

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
                url, block = bm
                return ("url", url, "bm", block)
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



def show_page(url, origin, start_block=0):
    try:
        html = fetch(url)
    except Exception as e:
        print(f"{C_ERR}{e}{C_RESET}")
        input("Enter…")
        return "home"

    paragraphs, links, main_image, page_title = extract_single_page(html, url)
    text_pages = build_text_pages(paragraphs)
    link_pages = list(paginate(links, 5))

    mode = "text"
    page = start_block if 0 <= start_block < len(text_pages) else 0
    next_part_loaded = False

    while True:
        clear_screen()
        cols = shutil.get_terminal_size().columns

        if mode == "text":
            # --- FIX: clamp page index to avoid crash ---
            if page >= len(text_pages):
                page = len(text_pages) - 1
            if page < 0:
                page = 0
            # -------------------------------------------

            for line in text_pages[page]:
                print(f"{C_TEXT}{line}{C_RESET}")
            print(f"{C_DIM}Block {page+1}/{len(text_pages)}{C_RESET} {C_CMD}Space/↓=next  p/↑=prev  l=links  i=image  b=back  m=save  bm=bookmarks  h=home  q=quit{C_RESET}")
        else:
            if link_pages and 0 <= page < len(link_pages):
                for i, (label, link) in enumerate(link_pages[page], 1):
                    short_label = label[:60] + "…" if len(label) > 60 else label
                    short_link = shorten_middle(link, cols - len(short_label) - 10)
                    print(f"{i}. {short_label} {C_DIM}→ {short_link}{C_RESET}")
                print(f"\n{C_DIM}Page {page+1}/{len(link_pages)}{C_RESET}")
            else:
                print("[No links]\n")

            print(f"{C_CMD}[SPACE]=next  p=prev  number=open  t=text  b=back  h=home  q=quit{C_RESET}")

        title_to_show = page_title if page_title else shorten_middle(url, cols - 6)
        print(f"{C_TEXT}{title_to_show}{C_RESET}")
        print("> ", end="", flush=True)
        key = read_key()

        # Arrow keys
        if key == "DOWN":
            c = "next"
        elif key == "UP":
            c = "p"

        # Space / Enter
        elif key == " ":
            c = "next"
        elif key == "\n":
            c = "next"

        # Backspace while typing a command
        elif key == "BACKSPACE":
            # Let user edit normally
            print("\b \b", end="", flush=True)
            rest = input()
            c = rest.strip().lower()

        # Normal typed commands
        else:
            print(key, end="", flush=True)
            rest = input()
            raw = key + rest
            c = raw.strip().lower()

        if c == "q":
            return "quit"
        if c == "h":
            return "home"
        if c == "b":
            if origin == "search":
                return "back_search"
            if origin == "bm":
                return "back_bm"
            return "home"
        if c == "m":
            save_bookmark(url, page, page_title)
            input("Saved. Enter…")
            continue
        if c == "bm":
            bm = bookmark_manager()
            if bm:
                return bm
            continue

        if mode == "text":
            if c == "l":
                mode = "links"
                page = 0
                continue
            if c == "next":
                if page < len(text_pages) - 1:
                    page += 1
                    continue

                # At last block: try to discover next part
                result = try_load_next_part(url, paragraphs)
                if result:
                    paragraphs, links, main_image, page_title, url = result
                    text_pages = build_text_pages(paragraphs)
                    link_pages = list(paginate(links, 5))
                    continue

                # No more content
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
            if c.isdigit() and link_pages:
                i = int(c) - 1
                if 0 <= page < len(link_pages) and 0 <= i < len(link_pages[page]):
                    return link_pages[page][i][1]

        input(f"{C_ERR}Invalid.{C_RESET} Enter…")

# ========= MAIN LOOP =========
def main():
    mode = "home"
    current_url = None
    origin = "direct"
    last_search_query = None
    start_block = 0

    while True:
        if mode == "home":
            action = home()
            if action[0] == "quit":
                break
            if action[0] == "bookmarks":
                mode = "bookmarks"
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

        elif mode == "search":
            res = search_and_select(last_search_query)
            if res is None:
                mode = "home"
                continue
            if res[0] == "quit":
                break
            if res[0] == "url":
                current_url = res[1]
                origin = res[2]
                start_block = res[3] if len(res) > 3 else 0
                mode = "page"
                continue

        elif mode == "bookmarks":
            bm = bookmark_manager()
            if bm is None:
                mode = "home"
                continue
            current_title, current_url, start_block = bm
            origin = "bm"
            mode = "page"
            continue

        elif mode == "page":
            nav = show_page(current_url, origin, start_block)
            if nav == "quit":
                break
            if nav == "home":
                mode = "home"
                current_url = None
                origin = "direct"
                start_block = 0
                continue
            if nav == "back_search":
                if last_search_query is None:
                    mode = "home"
                else:
                    mode = "search"
                continue
            if nav == "back_bm":
                mode = "bookmarks"
                continue
            if isinstance(nav, tuple):
                current_title, current_url, start_block = nav
                origin = "bm"
                mode = "page"
                continue
            if isinstance(nav, str):
                current_url = nav
                start_block = 0
                continue

if __name__ == "__main__":
    main()
