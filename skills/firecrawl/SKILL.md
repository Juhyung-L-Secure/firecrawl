---
name: firecrawl
description: Scrape entire API documentation sites into a local searchable markdown file using a local Firecrawl server. Auto-starts and stops the server.
---

# API Documentation Scraper

## Purpose

Scrape an entire API documentation website into a single local markdown file
so you can search it instantly with Grep instead of fetching web pages one at a time.

API docs span dozens or hundreds of pages. A local file lets you Grep for exact
method names, parameters, and examples without wasting context window on WebFetch.

---

## Paths and Output Folder

Use [scripts/paths.py](scripts/paths.py) to resolve this Firecrawl checkout and
read the saved output folder. It follows the helper's real path through symlinks;
never infer the repository from the current working directory.

Before checking the manifest or starting Firecrawl, run:

```bash
python3 "$HOME/.agents/skills/firecrawl/scripts/paths.py"
```

The JSON result contains `repo_dir`, `output_dir`, and `config_file`.

- If `output_dir` is `null`, ask the user once: "Which folder should store your
  crawled documentation? Give an absolute path or a path starting with `~/`."
  Wait for the answer, then save that exact choice with the helper:

  ```bash
  python3 "$HOME/.agents/skills/firecrawl/scripts/paths.py" --output-dir "USER_CHOSEN_FOLDER"
  ```

- The choice is recorded in `~/.config/firecrawl/skill.json`, outside the clone,
  and reused on later calls. Do not ask again unless the user requests a change.
- If the helper reports an invalid config or path, stop and report the error.
  Do not replace it with a default, another config file, or another output folder.

After the folder is configured, use this setup before each shell call that needs
repository or output paths; shell variables do not persist between tool calls:

```bash
set -e
FIRECRAWL_PATHS="$(python3 "$HOME/.agents/skills/firecrawl/scripts/paths.py")"
FIRECRAWL_REPO="$(printf '%s' "$FIRECRAWL_PATHS" | python3 -c 'import json, sys; print(json.load(sys.stdin)["repo_dir"])')"
SHARED_DIR="$(printf '%s' "$FIRECRAWL_PATHS" | python3 -c 'import json, sys; paths = json.load(sys.stdin); assert paths["output_dir"] is not None, "Output folder has not been configured"; print(paths["output_dir"])')"
MANIFEST="${SHARED_DIR}/manifest.json"
export SHARED_DIR MANIFEST
```

A `manifest.json` file in this directory maps source URLs to filenames:

```json
{
  "https://nextjs.org/docs/pages/getting-started": "nextjs_pages_docs.md",
  "https://docs.stripe.com/api": "stripe_api_docs.md"
}
```

**Filename convention:** Use a short, readable, snake_case name derived from the
domain and path (e.g., `nextjs_pages_docs.md`, `stripe_api_docs.md`).

---

## When to Use

- Before starting any project that uses an external API or library
- When the user says "scrape the docs for X"
- When you need to look up API details but don't know which page to fetch

## Do NOT Use When

- Documentation already exists locally and is up to date
- The API is simple enough that WebFetch on a single page is sufficient
- The user just needs a quick lookup (use WebFetch directly)

---

## Rules

- **Rule 1:** Always check the manifest FIRST (Phase 0). Skip the crawl if the URL is already listed.
- **Rule 2:** Always auto-start Firecrawl if it's not running. Never ask the user to start it.
- **Rule 3:** Always stop Firecrawl with `docker compose down` after the crawl is complete.
- **Rule 4:** Never skip the Discover phase — always analyze the site structure before crawling.
- **Rule 5:** Always set `allowExternalLinks: false` to prevent crawling off-domain.
- **Rule 6:** After saving, use Grep on the local file — never use WebFetch for scraped APIs.
- **Rule 7:** Save results only to the user-configured output folder.
- **Rule 8:** Always update `manifest.json` after saving a new crawl result.
- **Rule 9:** NEVER fall back to WebFetch. If Firecrawl/Docker is unavailable, stop and tell the user to install Docker first. Do not attempt to crawl pages manually with WebFetch as a workaround.

---

## Process

### Phase 0: Check Manifest for Existing Crawl Results

After resolving paths, check if the docs have already been scraped.

Read `manifest.json` and check if the target URL is a key. If it is, the value
is the filename of the existing crawl result.

```bash
if [ -f "${MANIFEST}" ]; then
  EXISTING=$(python3 -c "
import json, os, sys
with open(os.environ['MANIFEST']) as f:
    m = json.load(f)
url = 'THE_DOCS_URL'
if url in m:
    print(m[url])
" 2>/dev/null)
  if [ -n "${EXISTING}" ] && [ -f "${SHARED_DIR}/${EXISTING}" ]; then
    echo "✓ Crawl results already exist: ${SHARED_DIR}/${EXISTING}"
    echo "  Size: $(du -h "${SHARED_DIR}/${EXISTING}" | cut -f1)"
    echo "  Pages: $(grep -c '^# https\?://' "${SHARED_DIR}/${EXISTING}")"
    echo "Skipping crawl. Use Grep to search the file."
  fi
fi
```

**If found:** Stop here. Report the existing file and use Grep to search it.
**If not found:** Continue to Phase 1.

### Phase 1: Ensure Firecrawl is Running

Check if the server is up. If not, start it and wait for it to be ready.

```bash
if ! curl -s --max-time 5 http://localhost:3002/v1/health > /dev/null 2>&1; then
  echo "Firecrawl not running. Starting..."
  cd "$FIRECRAWL_REPO" && docker compose up -d
  for i in $(seq 1 12); do
    if curl -s --max-time 5 http://localhost:3002/v1/health > /dev/null 2>&1; then
      echo "Firecrawl is ready."
      break
    fi
    echo "Waiting for Firecrawl to start... ($i/12)"
    sleep 5
  done
  if ! curl -s --max-time 5 http://localhost:3002/v1/health > /dev/null 2>&1; then
    echo "ERROR: Firecrawl failed to start. Check docker compose logs in ${FIRECRAWL_REPO}."
    exit 1
  fi
else
  echo "Firecrawl already running."
fi
```

### Phase 2: Discover

Scrape the root API docs page to get all links and understand the site structure.

```bash
curl -s -X POST http://localhost:3002/v1/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "url": "THE_DOCS_URL",
    "formats": ["markdown", "links"]
  }'
```

Analyze the returned links and identify:
- The URL pattern for actual API doc pages (e.g., `/api/classes/*`, `/reference/*`)
- URLs to exclude (GitHub issues, blogs, changelogs, external sites)
- The depth of the docs

If the scrape returns empty or minimal content (JS-rendered site), use `/v1/map` as fallback:

```bash
curl -s -X POST http://localhost:3002/v1/map \
  -H "Content-Type: application/json" \
  -d '{
    "url": "THE_DOCS_URL",
    "limit": 500
  }'
```

### Phase 3: Filter

Build include/exclude patterns based on discovered links.

**Common includes:** `/api/`, `/reference/`, `/docs/api/`, `/classes/`, `/methods/`, `/sdk/`

**Common excludes:** `github.com`, `issues`, `blog`, `changelog`, `discord`, `login`, `pricing`

**Always set:**
- `allowExternalLinks: false`
- `allowBackwardLinks: false`
- `maxDepth: 3-5` (increase only if docs are deeply nested)

### Phase 4: Crawl

Execute the crawl with filters from Phase 3.

```bash
curl -s -X POST http://localhost:3002/v1/crawl \
  -H "Content-Type: application/json" \
  -d '{
    "url": "THE_DOCS_URL",
    "limit": 500,
    "includePaths": ["INCLUDE_PATTERN"],
    "excludePaths": ["EXCLUDE_PATTERN_1", "EXCLUDE_PATTERN_2"],
    "allowExternalLinks": false,
    "allowBackwardLinks": false,
    "maxDepth": 5,
    "scrapeOptions": {
      "formats": ["markdown"],
      "onlyMainContent": true
    }
  }'
```

Poll for completion every 15-30 seconds:

```bash
curl -s "http://localhost:3002/v1/crawl/JOB_ID" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'Status: {d[\"status\"]}, Pages: {d.get(\"completed\",0)}/{d.get(\"total\",\"?\")}')
"
```

### Phase 5: Save and Update Manifest

Fetch all results and save to the shared crawl results directory.

**Output location:** `SHARED_DIR`, loaded from the saved configuration.
**Filename:** Short, readable, snake_case name (e.g., `nextjs_pages_docs.md`)

```python
python3 -c "
import json, urllib.request, os

all_markdown = []
next_url = 'http://localhost:3002/v1/crawl/JOB_ID'

while next_url:
    req = urllib.request.Request(next_url)
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    for item in data.get('data', []):
        md = item.get('markdown', '')
        url = item.get('metadata', {}).get('sourceURL', '')
        if md and 'Page not found' not in md:
            all_markdown.append(f'# {url}\n\n{md}\n\n---\n\n')
    next_url = data.get('next', None)

shared_dir = os.environ['SHARED_DIR']
filename = 'FILENAME.md'
output_path = os.path.join(shared_dir, filename)
os.makedirs(shared_dir, exist_ok=True)

with open(output_path, 'w', encoding='utf-8') as f:
    f.writelines(all_markdown)

# Update manifest.json
manifest_path = os.path.join(shared_dir, 'manifest.json')
manifest = {}
if os.path.exists(manifest_path):
    with open(manifest_path) as f:
        manifest = json.load(f)

manifest['THE_DOCS_URL'] = filename

with open(manifest_path, 'w') as f:
    json.dump(manifest, f, indent=2)

print(f'Saved {len(all_markdown)} pages to {output_path}')
print(f'Updated manifest: {manifest_path}')
"
```

### Phase 6: Stop Firecrawl

After saving and verifying, shut down the server.

```bash
cd "$FIRECRAWL_REPO" && docker compose down
echo "Firecrawl server stopped."
```

---

## Verify

- [ ] File exists at the shared path
- [ ] File size is at least a few hundred KB
- [ ] Page count: `grep -c "^# https://" OUTPUT_PATH`
- [ ] No 404s: `grep -c "Page not found" OUTPUT_PATH` should be 0 or very low
- [ ] `manifest.json` contains the URL → filename mapping
- [ ] Spot check: read a few sections for method signatures and parameters
- [ ] Test search: `grep -i "SOME_METHOD_NAME" OUTPUT_PATH`
- [ ] Firecrawl server is stopped: `curl -s http://localhost:3002/v1/health` should fail

Report to user:
```
Scraped X pages from DOCS_URL
File: OUTPUT_PATH (Y MB)
404 pages filtered: N
Manifest updated: ✓
Firecrawl server: stopped
```
