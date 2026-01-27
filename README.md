# === TEXT BROWSER V.0 ===
web browser in terminal (also termux) in python
</br>

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



# Terminal Text Browser — Features Overview

## 🏠 Home Screen
- Accepts:
  - Direct URLs (`https://example.com`)
  - Domain shortcuts (`example.com`)
  - Search queries (sent to DuckDuckGo Lite)
- Commands:
  - `bm` — open bookmark manager
  - `q` — quit the application

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
  - `ENTER` — next block
  - `p` — previous block
  - `l` — switch to link mode
  - `b` — go back in history
  - `m` — save current page as bookmark
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
  - `bm` — open bookmark manager
  - `h` — home
  - `q` — quit

---

## 🔖 Bookmark Manager
- Stores bookmarks in `~/.tbrowser_bookmarks`
- Features:
  - List all saved URLs
  - Open a bookmark
  - Delete a bookmark (`d<number>`)
- Commands:
  - `<number>` — open bookmark
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

## 🧹 Content Extraction
- Removes:
  - Scripts
  - Styles
  - Headers/footers/navbars
- Detects main content block by size
- Extracts:
  - Paragraphs
  - List items
  - Links

---

## ⚙️ Configuration
- `SAFE_MODE` — block ad/tracker domains
- `STRIP_DDG_TRACKING` — remove DuckDuckGo tracking params
- `PARAS_PER_PAGE` — number of paragraphs per text page
- `DUCK_LITE` — search endpoint

