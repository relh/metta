---
name: cm.web
description: Browser automation inside cmux using the cmux browser CLI
---

Use the `cmux browser` CLI for browser automation. DO NOT use `mcp__claude-in-chrome__*` tools — they won't work inside cmux.

## Setup: Find or create a browser

1. List all panes to find one with a browser surface:

```bash
cmux list-panes
```

2. For each pane, check its surfaces:

```bash
cmux list-pane-surfaces --pane <pane>
```

Look for a surface showing a page title (not a terminal). If you find one, use it.

3. If no browser surface exists, open one:

```bash
cmux browser open <url>
```

This creates a new browser surface and returns its ref (e.g. `surface:6 pane=pane:5`). Use the surface ref for all subsequent commands.

**Surfaces can disappear** — if a command returns `not_found: Surface not found`, re-run `cmux list-panes` to discover what's available and create a new browser if needed.

## Commands

All commands use `cmux browser --surface <surface> <command>`.

### Navigation
- `navigate <url>` — go to a URL
- `back` / `forward` / `reload` — history navigation
- `get-url` — get current URL
- `get title` — get page title

### Reading the page
- `snapshot --interactive` — DOM snapshot with interactive element refs (best for finding what to click/fill)
- `snapshot --compact` — compact DOM snapshot (truncates on content-heavy pages)
- `get html [selector]` — get HTML content
- `get value <selector>` — get input value
- `get count <selector>` — count matching elements

**Note**: `get text` requires a selector — it does not work without one. To get all visible text from a page, use `eval` instead:

```bash
cmux browser --surface <surface> eval "document.body.innerText.substring(0, 5000)"
```

### Interacting
- `click <selector>` — click an element (CSS selector)
- `dblclick <selector>` — double-click
- `hover <selector>` — hover over element
- `type <selector> <text>` — type text (appends)
- `fill <selector> <text>` — fill input (replaces content; empty text clears)
- `press <key>` — press keyboard key (e.g. `Enter`, `Tab`, `Escape`)
- `select <selector> <value>` — select dropdown option
- `check <selector>` / `uncheck <selector>` — toggle checkboxes
- `scroll --dy -300` — scroll down (negative = down, positive = up)

### Waiting
- `wait --selector <css>` — wait for element to appear
- `wait --text <text>` — wait for text to appear
- `wait --url-contains <text>` — wait for URL change
- `wait --load-state complete` — wait for page load

### JavaScript
- `eval <script>` — evaluate JS and return result

### Tabs
- `tab list` — list browser tabs
- `tab new [url]` — open new tab
- `tab switch <index>` — switch to tab
- `tab close [index]` — close tab

### Console & errors
- `console list` — read console messages
- `errors list` — read page errors

### Other
- `find role <role>` / `find text <text>` / `find label <text>` — find elements by accessibility properties
- `highlight <selector>` — visually highlight an element
- `cookies get [name]` / `cookies set <name> <value>` / `cookies clear` — manage cookies
- `storage local get [key]` / `storage local set <key> <value>` — localStorage

## Data extraction with eval

`snapshot` truncates on content-heavy pages. For extracting structured data (search results, listings, tables), use `eval` with JavaScript:

```bash
# Get all visible text from a specific section
cmux browser --surface <surface> eval "document.querySelector('[role=\"main\"]')?.innerText"

# Extract a list of items with their details
cmux browser --surface <surface> eval "
var items = document.querySelectorAll('.result-item');
var out = [];
for (var i = 0; i < items.length; i++) {
  out.push(items[i].innerText.replace(/[\\n\\r]+/g, ' | ').trim());
}
out.join('\\n');
"
```

### Lazy-loaded content

Many sites load results incrementally as you scroll. If you're only seeing a few results, scroll the container to trigger loading:

```bash
cmux browser --surface <surface> eval "
var list = document.querySelector('[class*=\"list\"]');
if (list) { list.scrollTop = list.scrollHeight; }
"
```

Then re-extract. You may need to scroll multiple times for very long lists.

## Workflow

1. **Find or create browser**: `cmux list-panes` → `cmux list-pane-surfaces --pane <pane>` → use existing surface, or `cmux browser open <url>` to create one
2. **Check current state**: `get-url` and `get title`
3. **Navigate if needed**: `navigate <url>`
4. **Read the page**: `snapshot --interactive` for interaction, `eval` for data extraction
5. **Interact**: click, type, fill as needed (use `--snapshot-after` flag to see result)
6. **Verify**: check URL, text, or snapshot to confirm success

## Tips

- Add `--snapshot-after` to any interaction command to get a DOM snapshot after the action
- Use `snapshot --interactive` to see clickable elements with their selectors
- Use `wait` before interacting with dynamically-loaded content
- The `--selector` flag on `snapshot` lets you focus on a specific part of the page
- **Geolocation is unreliable** — "near me" queries may resolve to the wrong location. Use explicit addresses when location matters.
