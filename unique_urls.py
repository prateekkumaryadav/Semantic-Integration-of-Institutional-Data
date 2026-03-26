# -------- FILE NAMES --------
file1 = "all_urls.txt"
file2 = "all_urls1.txt"
output_file = "unique_urls.txt"


# -------- CLEAN URL --------
def clean_url(line):
    line = line.strip()

    if line.startswith("Visiting:"):
        line = line.replace("Visiting:", "").strip()

    return line.rstrip("/")


# -------- FILTER --------
def is_valid(url):
    if not url.startswith("http"):
        return False

    BAD_KEYWORDS = [
        "faculty-articles",
        "stories",
        "sitemap",
        "nirf",
        "iqac",
        "privacy",
        "feedback",
        "careers",
        "tenders"
    ]

    if any(k in url.lower() for k in BAD_KEYWORDS):
        return False

    return True


# -------- READ + MERGE --------
urls = set()

for file in [file1, file2]:
    with open(file, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            url = clean_url(line)

            if url and is_valid(url):
                urls.add(url)


# -------- SORT --------
unique_urls = sorted(urls)


# -------- WRITE TO FILE --------
with open(output_file, "w", encoding="utf-8") as f:
    for url in unique_urls:
        f.write(url + "\n")


# -------- PRINT --------
print(f"\n✅ Saved {len(unique_urls)} unique URLs to '{output_file}'")