#!/usr/bin/env python3
import os
import shutil
import requests
from bs4 import BeautifulSoup
from urllib.parse import (
    urljoin,
    urlparse,
    parse_qs,
    unquote,
    urlunparse,
    urlencode,
)

# ========= CONFIG =========
SAFE_MODE = True          # hide obvious ad/tracker links
STRIP_DDG_TRACKING = True # remove DuckDuckGo tracking params
DUCK_LITE = "https://lite.duckduckgo.com/lite/"
BOOKMARK_FILE = os.path.expanduser("~/.tbrowser_bookmarks")

# ========= COLORS =========
C_RESET = "\033[0m"
C_TITLE = "\033[96m"
C_LINK = "\033[93m"
C_CMD = "\033[92m"
C_ERR = "\033[91m"
C_DIM = "\033[90m"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"
})


# ========= BOOKMARKS =========
def load_bookmarks():
    if not os.path.exists(BOOKMARK_FILE):
        return []
    with open(BOOKMARK_FILE, "r") as f:
        return [line.strip() for line in f if line.strip()]


def save_bookmark(url):
    with open(BOOKMARK_FILE, "a") as f:
        f.write(url + "\n")


# ========= URL HELPERS =========
def normalize_url(text):
    text = text.strip()
    if text.startswith("http://") or text.startswith("https://"):
        return text
    if "." in text:
        return "https://" + text
    return None


def strip_duckduckgo_tracking(url):
    if not STRIP_DDG_TRACKING:
        return url
    parsed = urlparse(url)
    if "duckduckgo.com" not in parsed.netloc:
        return url
    qs = parse_qs(parsed.query)
    allowed = {}
    new_query = urlencode(allowed, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def unwrap_duckduckgo_redirect(url):
    if url.startswith("//duckduckgo.com/l/?"):
        url = "https:" + url

    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l"):
        qs = parse_qs(parsed.query)
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
    return url


def unwrap_generic_redirect(url):
    url = unwrap_duckduckgo_redirect(url)
    url = strip_duckduckgo_tracking(url)
    return url


def is_ad_or_tracker(url):
    if not SAFE_MODE:
        return False
    host = urlparse(url).netloc.lower()
    bad_keywords = [
        "doubleclick",
        "adservice",
        "adsystem",
        "tracking",
        "analytics",
        "pixel",
        "clickserve",
        "googlesyndication",
    ]
    return any(k in host for k in bad_keywords)


# ========= FETCH & PARSE =========
def fetch(url):
    r = session.get(url, timeout=15)
    r.raise_for_status()
    return r.text


def extract(html, base):
    soup = BeautifulSoup(html, "html.parser")

    candidates = []
    for tag in soup.find_all(["article", "main", "div"]):
        size = len(tag.get_text(strip=True))
        candidates.append((size, tag))
    candidates.sort(reverse=True, key=lambda x: x[0])
    main = candidates[0][1] if candidates else soup.body or soup

    paragraphs = []
    for p in main.find_all(["p", "li"]):
        text = " ".join(p.get_text(" ", strip=True).split())
        if len(text) > 40:
            paragraphs.append(text)

    links = []
    for a in main.find_all("a", href=True):
        label = a.get_text(" ", strip=True)
        href = urljoin(base, a["href"])
        href = unwrap_generic_redirect(href)
        if is_ad_or_tracker(href):
            continue
        links.append((label if label else href, href))

    return paragraphs, links


def paginate(items, page_size=20):
    for i in range(0, len(items), page_size):
        yield items[i:i + page_size]


# ========= SEARCH =========
def search_duck(query):
    r = session.get(DUCK_LITE + "?q=" + query, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    results = []
    for a in soup.select("a.result-link"):
        title = a.get_text(" ", strip=True)
        href = a.get("href")
        if not href:
            continue
        href = unwrap_generic_redirect(href)
        if is_ad_or_tracker(href):
            continue
        results.append((title, href))
    return results


# ========= UI HELPERS =========
def clear_screen():
    os.system("clear")


def print_search_results(results):
    clear_screen()
    print(f"{C_TITLE}=== SEARCH RESULTS ==={C_RESET}\n")
    for i, (title, url) in enumerate(results, 1):
        print(f"{C_LINK}{i}. {C_RESET}{title}")
        print(f"   {C_DIM}{url}{C_RESET}")
    print()
    print(f"{C_CMD}Select number, 'h' for home, 'q' to quit.{C_RESET}")


def home():
    while True:
        print(f"\n{C_TITLE}=== HOME ==={C_RESET}")
        print("Enter search text or URL:")
        text = input("> ").strip()

        if not text:
            continue

        url = normalize_url(text)
        if url:
            return url

        print(f"{C_TITLE}\nSearching DuckDuckGo…{C_RESET}")
        results = search_duck(text)

        if not results:
            print(f"{C_ERR}No results found.{C_RESET}")
            continue

        while True:
            print_search_results(results)
            c = input("Result> ").strip().lower()
            if c == "q":
                raise SystemExit
            if c == "h":
                break
            if c.isdigit():
                idx = int(c)
                if 1 <= idx <= len(results):
                    return results[idx - 1][1]
                else:
                    print(f"{C_ERR}Invalid number.{C_RESET}")
            else:
                print(f"{C_ERR}Invalid input.{C_RESET}")


# ========= PAGE VIEW =========
def show_page(url, history):
    try:
        html = fetch(url)
    except Exception as e:
        print(f"{C_ERR}Error: {e}{C_RESET}")
        input("Press Enter…")
        return None

    paragraphs, links = extract(html, url)

    text_pages = list(paginate(paragraphs, page_size=15))
    link_pages = list(paginate(links, page_size=20))

    mode = "text"   # "text" or "links"
    page_index = 0

    while True:
        clear_screen()
        width = shutil.get_terminal_size().columns

        print(f"{C_TITLE}URL: {url}{C_RESET}")
        print("=" * width)

        # ----- TEXT MODE -----
        if mode == "text":
            print(f"{C_TITLE}--- TEXT ---{C_RESET}\n")

            if text_pages:
                for p in text_pages[page_index]:
                    print(p + "\n")
                print(f"{C_DIM}Page {page_index + 1}/{len(text_pages)}{C_RESET}")
            else:
                print("[No readable text]\n")

            print(f"\n{C_CMD}Commands:{C_RESET}")
            print("  n/p    = next/prev text page")
            print("  l      = switch to links")
            print("  b      = back")
            print("  h      = home")
            print("  m      = bookmark")
            print("  bm     = show bookmarks")
            print("  q      = quit")

        # ----- LINK MODE -----
        else:
            print(f"{C_TITLE}--- LINKS ---{C_RESET}\n")

            if link_pages:
                for i, (label, link) in enumerate(link_pages[page_index], 1):
                    short = (label[:60] + "…") if len(label) > 60 else label
                    print(f"{i}. {short} {C_DIM}→ {link}{C_RESET}")
                print(f"\n{C_DIM}Page {page_index + 1}/{len(link_pages)}{C_RESET}")
            else:
                print("[No links]\n")

            print(f"\n{C_CMD}Commands:{C_RESET}")
            print("  number = open link")
            print("  n/p    = next/prev link page")
            print("  t      = switch to text")
            print("  b      = back")
            print("  h      = home")
            print("  m      = bookmark")
            print("  bm     = show bookmarks")
            print("  q      = quit")

        cmd = input("\nCommand> ").strip().lower()

        # ===== Global commands =====
        if cmd == "q":
            raise SystemExit

        if cmd == "h":
            return None

        if cmd == "b":
            return history.pop() if history else None

        if cmd == "m":
            save_bookmark(url)
            print("Bookmarked.")
            input("Press Enter…")
            continue

        if cmd == "bm":
            bms = load_bookmarks()
            clear_screen()
            print(f"{C_TITLE}=== BOOKMARKS ==={C_RESET}\n")
            if not bms:
                print("No bookmarks yet.")
            else:
                for i, u in enumerate(bms, 1):
                    print(f"{i}. {u}")
            input("\nPress Enter…")
            continue

        # ===== Text mode navigation =====
        if mode == "text":
            if cmd == "l":
                mode = "links"
                page_index = 0
                continue

            if cmd == "n" and page_index < len(text_pages) - 1:
                page_index += 1
                continue

            if cmd == "p" and page_index > 0:
                page_index -= 1
                continue

        # ===== Link mode navigation =====
        else:
            if cmd == "t":
                mode = "text"
                page_index = 0
                continue

            if cmd == "n" and page_index < len(link_pages) - 1:
                page_index += 1
                continue

            if cmd == "p" and page_index > 0:
                page_index -= 1
                continue

            if cmd.isdigit():
                idx = int(cmd)
                if 1 <= idx <= len(link_pages[page_index]):
                    raw = link_pages[page_index][idx - 1][1]
                    clean = unwrap_generic_redirect(raw)
                    return clean

        print(f"{C_ERR}Invalid command.{C_RESET}")
        input("Press Enter…")


# ========= MAIN LOOP =========
def main():
    history = []
    current = None

    while True:
        if current is None:
            current = home()

        history.append(current)
        next_url = show_page(current, history)

        if next_url is None:
            current = None
        else:
            current = next_url


if __name__ == "__main__":
    main()
