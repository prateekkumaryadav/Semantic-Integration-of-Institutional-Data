"""
IIITB Website Crawler
=====================
BFS-based, concurrent, requests+BS4 crawler.
Finds every internal URL reachable from BASE_URL.

Usage:
    pip install requests beautifulsoup4 lxml
    python crawler.py

Output:
    - Live progress to stdout
    - all_urls.txt   → flat list of every URL found
    - sitemap.json   → full parent→children adjacency map
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlunparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import json
import time
import sys

# ─────────────────────── CONFIG ───────────────────────
BASE_URL        = "https://www.iiitb.ac.in"
MAX_WORKERS     = 10          # concurrent threads (be polite; don't hammer the server)
REQUEST_TIMEOUT = 10          # seconds per request
DELAY_BETWEEN   = 0.2         # seconds between requests per thread
MAX_PAGES       = 2000        # hard safety cap (set to None for unlimited)
SKIP_EXTENSIONS = {           # don't bother downloading binary files
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".tar", ".gz",
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico",
    ".mp4", ".mp3", ".avi", ".mov",
    ".css", ".js", ".woff", ".woff2", ".ttf", ".eot",
}
OUTPUT_TXT      = "all_urls.txt"
OUTPUT_JSON     = "sitemap.json"
# ──────────────────────────────────────────────────────

BASE_NETLOC = urlparse(BASE_URL).netloc

# ── Shared state (thread-safe) ──
visited_lock = threading.Lock()
visited: set[str] = set()
adjacency: dict[str, list[str]] = {}  # parent → [children]
adjacency_lock = threading.Lock()
queue: deque[str] = deque()
queue_lock = threading.Lock()
found_count = 0
found_lock = threading.Lock()

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (compatible; SiteMapper/1.0; "
        "+https://github.com/your-repo)"
    )
})


# ─────────────────────── HELPERS ──────────────────────

def normalize(url: str) -> str:
    """Canonical form: strip fragment, lowercase scheme+host, remove trailing slash."""
    p = urlparse(url)
    # lowercase scheme and netloc, keep path case
    path = p.path.rstrip("/") or "/"
    # drop fragment; keep query (search pages differ by query)
    clean = urlunparse((p.scheme.lower(), p.netloc.lower(), path, p.params, p.query, ""))
    return clean


def is_internal(url: str) -> bool:
    netloc = urlparse(url).netloc.lower()
    return netloc == BASE_NETLOC or netloc == "" or netloc.endswith("." + BASE_NETLOC)


def should_skip(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in SKIP_EXTENSIONS)


def extract_links(html: str, page_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith("javascript") or href.startswith("mailto") or href.startswith("tel"):
            continue
        full = normalize(urljoin(page_url, href))
        if is_internal(full) and not should_skip(full):
            links.append(full)
    return links


def fetch_and_parse(url: str) -> tuple[str, list[str]]:
    """Return (url, children). children=[] on error."""
    time.sleep(DELAY_BETWEEN)
    try:
        resp = SESSION.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        # Follow redirects: record the final URL as canonical
        final_url = normalize(resp.url)
        content_type = resp.headers.get("Content-Type", "")
        if "text/html" not in content_type:
            return final_url, []
        children = extract_links(resp.text, final_url)
        return final_url, children
    except Exception as e:
        print(f"   ✗ {url}  ({e})", file=sys.stderr)
        return url, []


# ─────────────────────── CRAWLER ──────────────────────

def crawl():
    global found_count

    start_url = normalize(BASE_URL)
    visited.add(start_url)
    queue.append(start_url)

    print(f"Starting crawl from: {start_url}")
    print(f"Workers: {MAX_WORKERS}  |  Max pages: {MAX_PAGES or '∞'}\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {}

        def submit_next():
            """Pull up to MAX_WORKERS URLs from the queue and submit them."""
            with queue_lock:
                batch = []
                while queue and len(futures) + len(batch) < MAX_WORKERS * 2:
                    url = queue.popleft()
                    batch.append(url)
            for u in batch:
                futures[pool.submit(fetch_and_parse, u)] = u

        submit_next()

        while futures:
            done_futures = []
            # Collect any completed futures
            for f in list(futures.keys()):
                if f.done():
                    done_futures.append(f)

            if not done_futures:
                time.sleep(0.05)
                continue

            for f in done_futures:
                parent = futures.pop(f)
                final_url, children = f.result()

                # If redirect changed the URL, also mark final as visited
                with visited_lock:
                    visited.add(final_url)

                new_children = []
                for child in children:
                    with visited_lock:
                        if child in visited:
                            continue
                        if MAX_PAGES and len(visited) >= MAX_PAGES:
                            continue
                        visited.add(child)

                    new_children.append(child)
                    with queue_lock:
                        queue.append(child)

                with adjacency_lock:
                    adjacency[final_url] = new_children

                with found_lock:
                    found_count = len(visited)

                status = f"[{found_count:>4} found] ✓ {final_url}"
                if new_children:
                    status += f"  → {len(new_children)} new links"
                print(status)

            submit_next()

            # Stop if hit cap
            if MAX_PAGES and found_count >= MAX_PAGES:
                print(f"\nReached MAX_PAGES cap ({MAX_PAGES}). Stopping.")
                break


# ─────────────────────── OUTPUT ───────────────────────

def save_results():
    all_urls = sorted(visited)

    with open(OUTPUT_TXT, "w") as f:
        for url in all_urls:
            f.write(url + "\n")
    print(f"\n✅ {len(all_urls)} URLs saved to {OUTPUT_TXT}")

    with open(OUTPUT_JSON, "w") as f:
        json.dump(adjacency, f, indent=2)
    print(f"✅ Adjacency map saved to {OUTPUT_JSON}")

    # Quick domain breakdown
    from collections import Counter
    paths = [urlparse(u).path.split("/")[1] for u in all_urls if urlparse(u).path != "/"]
    top = Counter(paths).most_common(15)
    print("\nTop path prefixes:")
    for prefix, count in top:
        print(f"   /{prefix:<30}  {count} pages")


# ──────────────────────── MAIN ────────────────────────

if __name__ == "__main__":
    t0 = time.time()
    try:
        crawl()
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        elapsed = time.time() - t0
        print(f"\nCrawl finished in {elapsed:.1f}s  |  {len(visited)} pages visited")
        save_results()