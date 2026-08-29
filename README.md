# TERMINAL TEXT BROWSER 
A terminal‑friendly web browser built for comfortable reading on small devices. It turns websites into clean, book‑style pages and remembers exactly where you left off — down to the last paragraph — with automatic progress saving for bookmarked pages. Continous Wattpad stories reading by automatic chapter change.
</br>
A terminal version of the android app here : https://github.com/adegard/TextBrowserApp/

# Features Overview

## 🏠 Home Screen
- Accepts:
  - Direct URLs (`https://example.com`)
  - Domain shortcuts (`example.com`)
  - Search queries (sent to DuckDuckGo Lite, check other provider in settings), also 'ifl'+text = for "I'm feeling lucky" search-method, which takes the first result)
  - Ask AI in terminal (you need to set Groq API - in Settings)
  - Automatic page/chapter switch on Wattpad stories
- Commands:
  - `bm` — open bookmark manager
  - `c` — open chronology
  - `ai your_question` — ask ai (put groq api key in settings first) 
  - `q` — quit the application
  - `s` — settings
---

## 🔍 Search
- Uses DuckDuckGo Lite for lightweight HTML results
- Displays:
  - Result title
  - Cleaned URL (tracking removed)
- Commands:
  - `<number>` — open selected result
  - `bm` — open bookmark manager
  - `h` — return to home
  - `q` — quit

---

## 📄 Page View

### Text Mode
- Extracts main readable content from the page
- Cleans paragraphs and wraps them to terminal width
- Pagination by paragraph blocks
- Commands:
  - `SPACE/↓` — next block
  - `p/↑` — previous block
  - `l` — switch to link mode
  - `b` — go back on search results
  - `bc` — go back in chronology (last visited page)
  - `m` — save current page and block as bookmark
  - `s` — share (show full url and tiny url to be copied)
  - `ai + text` — ask something to ai
  - `ai` — ask ai to comment the current block of text
  - `bm` — open bookmark manager
  - `h` — home
  - `q` — quit

### Link Mode
- Lists all extracted links from the page
- Paginated in groups of 20
- Commands:
  - `<number>` — open selected link
  - `ENTER` — next link page
  - `p` — previous link page
  - `t` — return to text mode
  - `b` — go back in history
  - `i` — show main image in terminal (block-colors)
  - `bm` — open bookmark manager
  - `h` — home
  - `q` — quit

---

## 🔖 Bookmark Manager
- Stores bookmarks in `~/.tbrowser_bookmarks`
- Features:
  - List all saved URLs, with last read block
  - Open a bookmark
  - Delete a bookmark (`d<number>`)
- Commands:
  - `<number>` — open bookmark, at last read block
  - `d<number>` — delete bookmark
  - `q` — return to previous screen

---

## 🌐 URL Handling
- Normalizes user input into valid URLs
- Removes DuckDuckGo tracking parameters
- Unwraps redirect links
- Filters ads and trackers (Safe Mode)

---

## 🧭 Navigation History
- Maintains a stack of visited pages
- `b` returns to the previous page
- History is session‑local (not saved to disk)

---

# Installation

pip install -r requirements.txt

python text_browser.py

# Updating

The script automatically check for new version at startup

## 🧹 HTML Content Extraction & PDF parsing
- Removes:
  - Scripts
  - Styles
  - Headers/footers/navbars
- Detects main content block by size
- Incremental pagination (tested on Wattpad, with url change while scrolling eg. /page/2 ..etc) 
- Extracts:
  - Paragraphs
  - List items
  - Links

---

![Screenshot](screen.jpg?raw=true "Screenshot")

---

For an overview of all my other projects, see https://adegard.github.io/blog/
