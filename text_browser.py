#!/usr/bin/env python3
import os
import re
import shutil
import requests
import json
from bs4 import BeautifulSoup
from urllib.parse import (
    urljoin, urlparse, parse_qs, unquote,
    urlunparse
)

# ========= CONFIG =========



SAFE_MODE = True
STRIP_DDG_TRACKING = True


SEARCH_ENGINES = {
    "duck_lite": "DuckDuckGo Lite",
    "duck_html": "DuckDuckGo HTML",
    "brave": "Brave Search",
    "google": "Google (text mode)",
    "bing": "Bing (text mode)"
}

CONFIG_FILE = os.path.expanduser("~/.tbrowser_config.json")

DEFAULT_CONFIG = {
    "PARAS_PER_PAGE": 2,
    "DEFAULT_ENGINE": "duck_lite"
}


BOOKMARK_FILE = os.path.expanduser("~/.tbrowser_bookmarks")


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
    except Exception:
        return DEFAULT_CONFIG.copy()

    # ensure missing keys are filled
    cfg = DEFAULT_CONFIG.copy()
    cfg.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})
    return cfg


def save_config():
    cfg = {
        "PARAS_PER_PAGE": PARAS_PER_PAGE,
        "DEFAULT_ENGINE": DEFAULT_ENGINE
    }
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

cfg = load_config()
PARAS_PER_PAGE = cfg["PARAS_PER_PAGE"]
DEFAULT_ENGINE = cfg["DEFAULT_ENGINE"]



# ========= COLORS =========
C_RESET = "\033[0m"
C_TITLE = "\033[96m"
C_LINK = "\033[93m"
C_CMD = "\033[92m"
C_ERR = "\033[91m"
C_DIM = "\033[90m"

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
    with open(BOOKMARK_FILE) as f:
        return [x.strip() for x in f if x.strip()]

def save_bookmark(url):
    with open(BOOKMARK_FILE, "a") as f:
        f.write(url + "\n")

def delete_bookmark(i):
    b = load_bookmarks()
    if 0 <= i < len(b):
        del b[i]
        with open(BOOKMARK_FILE, "w") as f:
            for x in b:
                f.write(x + "\n")

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

def extract(html, base):
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    # MAIN IMAGE
    main_image = fetch_main_image_url(soup, base)

    # MAIN CONTENT
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

    return paragraphs, links, main_image


def chunk_paragraphs(paragraphs, n):
    for i in range(0, len(paragraphs), n):
        yield paragraphs[i:i+n]

def paginate(items, n=20):
    for i in range(0, len(items), n):
        yield items[i:i+n]

# ========= SEARCH =========
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

def search_duck(q):
    url = "https://lite.duckduckgo.com/lite/?q=" + q
    r = session.get(url, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    results = []
    for a in soup.select("a.result-link"):
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
    # Using textise proxy to avoid JS
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
    return results


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
        return text[:max_len]  # fallback

    keep = (max_len - 3) // 2
    return text[:keep] + "..." + text[-keep:]


# ========= UI =========
def clear_screen():
    os.system("clear")

def print_search_results(results):
    clear_screen()
    print(f"{C_TITLE}=== SEARCH RESULTS ==={C_RESET}\n")
    for i, (title, url) in enumerate(results, 1):
        print(f"{C_LINK}{i}. {C_RESET}{title}")
        cols = shutil.get_terminal_size().columns
        short_url = shorten_middle(url, cols - 6)
        print(f"{C_TITLE}URL: {short_url}{C_RESET}")
        # print(f"   {C_DIM}{url}{C_RESET}")
    print()
    print(f"{C_CMD}Select number, bm=bookmarks, h=home, q=quit{C_RESET}")

def settings_menu():
    global PARAS_PER_PAGE, DEFAULT_ENGINE

    while True:
        clear_screen()
        print(f"{C_TITLE}=== SETTINGS ==={C_RESET}\n")
        print(f"1. Paragraphs per page: {PARAS_PER_PAGE}")
        print(f"2. Search engine: {SEARCH_ENGINES[DEFAULT_ENGINE]}")
        print("\nq = back\n")

        c = input("> ").strip().lower()

        if c == "q":
            return

        if c == "1":
            val = input("Paragraphs per page (1-20): ").strip()
            if val.isdigit() and 1 <= int(val) <= 20:
                PARAS_PER_PAGE = int(val)
                save_config()
            continue

        if c == "2":
            clear_screen()
            print(f"{C_TITLE}=== SEARCH ENGINES ==={C_RESET}\n")
            for i, (key, name) in enumerate(SEARCH_ENGINES.items(), 1):
                print(f"{i}. {name}")
            print("\nq = back\n")

            s = input("> ").strip().lower()
            if s == "q":
                continue
            if s.isdigit():
                idx = int(s) - 1
                if 0 <= idx < len(SEARCH_ENGINES):
                    DEFAULT_ENGINE = list(SEARCH_ENGINES.keys())[idx]
                    save_config()
            continue


def home():
    while True:
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
        print(f"{C_DIM}(Search / Url / bm=bookmarks / s=settings){C_RESET}")

        t = input("> ").strip().lower()
        if not t:
            continue

        # NEW: open bookmarks directly from home
        if t == "bm":
            bm = bookmark_manager()
            if bm:
                return bm
            continue
        
        if t == "s":
            settings_menu()
            continue


        url = normalize_url(t)
        if url:
            return url

        # Perform search
        results = search_duck(t)
        if not results:
            print(f"{C_ERR}No results.{C_RESET}")
            continue

        # SEARCH RESULTS LOOP
        while True:
            print_search_results(results)
            c = input("Result> ").strip().lower()

            # NEW: open bookmarks from results list
            if c == "bm":
                bm = bookmark_manager()
                if bm:
                    return bm
                continue

            if c == "q":
                raise SystemExit
            if c == "h":
                break
            if c.isdigit():
                i = int(c)
                if 1 <= i <= len(results):
                    return results[i-1][1]


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

        for i, u in enumerate(b, 1):
            print(f"{i}. {u}")

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
                return b[i]

# ========= PAGE VIEW =========
def build_text_pages(paragraphs):
    if not paragraphs:
        return [["[No readable text]"]]

    pages = []
    for block in chunk_paragraphs(paragraphs, PARAS_PER_PAGE):
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


def show_page(url, history):
    try:
        html = fetch(url)
    except Exception as e:
        print(f"{C_ERR}{e}{C_RESET}")
        input("Enter…")
        return None

    paragraphs, links, main_image = extract(html, url)
    text_pages = build_text_pages(paragraphs)
    link_pages = list(paginate(links, 5))

    mode = "text"
    page = 0

    while True:
        clear_screen()
        cols = shutil.get_terminal_size().columns

        #print("=" * cols)

        if mode == "text":
            for line in text_pages[page]:
                print(line)
            print(f"\n{C_DIM}Block {page+1}/{len(text_pages)} ...press [ENTER] next{C_RESET}")
            #print(f"{C_CMD}p=prev  l=links  b=back  m=bookmark  bm=saved  h=home  q=quit{C_RESET}")
            print(f"{C_CMD}p=prev  l=links  i=image  b=back  m=bookmark  bm=saved  h=home  q=quit{C_RESET}")

        else:
            if link_pages and 0 <= page < len(link_pages):
                for i, (label, link) in enumerate(link_pages[page], 1):
                    cols = shutil.get_terminal_size().columns
                    short_label = label[:60] + "…" if len(label) > 60 else label
                    short_link = shorten_middle(link, cols - len(short_label) - 10)
                    print(f"{i}. {short_label} {C_DIM}→ {short_link}{C_RESET}")
                print(f"\n{C_DIM}Page {page+1}/{len(link_pages)}{C_RESET}")
            else:
                print("[No links]\n")

            print(f"{C_CMD}[ENTER]=next  p=prev  number=open  t=text  b=back  h=home  q=quit{C_RESET}")
        cols = shutil.get_terminal_size().columns
        short_url = shorten_middle(url, cols - 6)
        print(f"{C_TITLE}{short_url}{C_RESET}")
        raw = input("> ")
        c = raw.strip().lower()

        # ENTER only → next
        if raw == "":
            c = "next"

        # Global
        if c == "q":
            raise SystemExit
        if c == "h":
            return None
        if c == "b":
            return history.pop() if history else None
        if c == "m":
            save_bookmark(url)
            input("Saved. Enter…")
            continue
        if c == "bm":
            bm = bookmark_manager()
            if bm:
                return bm
            continue

        # TEXT MODE
        if mode == "text":
            if c == "l":
                mode = "links"
                page = 0
                continue
            if c == "next" and page < len(text_pages) - 1:
                page += 1
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


        # LINK MODE
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

# ========= IMAGE RENDERING (HALF BLOCK) =========
from PIL import Image
import requests
from io import BytesIO

def fetch_main_image_url(soup, base_url):
    """
    Try to extract the main article image.
    Priority:
    1. <meta property="og:image">
    2. <img> inside main content
    """
    # 1. OG:image
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return urljoin(base_url, og["content"])

    # 2. First <img> inside main content
    img = soup.find("img")
    if img and img.get("src"):
        return urljoin(base_url, img["src"])

    return None


def render_image_halfblocks(img, max_width):
    """
    Convert an image to terminal half-blocks (▀ / ▄).
    Auto-resizes to terminal width.
    """
    # Convert to RGB
    img = img.convert("RGB")

    # Each terminal column = 1 pixel wide, but 2 pixels tall (top+bottom)
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

            # ANSI 24-bit color
            line += (
                f"\033[38;2;{top[0]};{top[1]};{top[2]}m"
                f"\033[48;2;{bottom[0]};{bottom[1]};{bottom[2]}m▀"
            )
        line += "\033[0m"
        lines.append(line)

    return lines


def show_image_in_terminal(url):
    """
    Download and render the image in half-block mode.
    """
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content))
    except Exception as e:
        return [f"[Image error: {e}]"]

    cols = shutil.get_terminal_size().columns
    max_width = max(20, cols - 2)

    return render_image_halfblocks(img, max_width)

# ========= MAIN LOOP =========
def main():
    history = []
    current = None

    while True:
        if current is None:
            current = home()
        history.append(current)
        current = show_page(current, history)

if __name__ == "__main__":
    main()
