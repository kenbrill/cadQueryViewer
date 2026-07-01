# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the viewer

```bash
# Start (drops viewer.py into a directory with .stl files)
.venv/bin/python viewer.py

# Or use the slash command in Claude Code (copies viewer.py, installs Flask, starts server)
/stl-viewer
```

The server auto-detects a free port starting at 7173 and opens the browser automatically. Running `/stl-viewer` a second time stops the server and removes `viewer.py`.

## Architecture

`viewer.py` is a single self-contained file meant to be dropped into any directory with `.stl` files. It has no external template files — all HTML, CSS, and JavaScript are inline Python strings.

**Backend (Flask)**:
- `index_page()` / `detail_page()` — generate full HTML pages as Python strings
- `parse_params()` — regex-extracts editable parameters from the `# PARAMETERS` section of CadQuery `.py` source files
- `patch_params()` — regex-rewrites parameter assignments in source text for Run/Save
- `run_script()` — executes `.py` scripts in a subprocess using `.venv/bin/python` if present, otherwise `sys.executable`
- `find_source_py()` — associates an STL with its generator script by filename match, then string search for the STL name in `.py` files
- Draft file pattern: Run uses `<stem>_draft.py` (patched copy) so the original isn't modified until Save is clicked

**REST API** (`/api/run/<stem>`, `/api/revert/<stem>`, `/api/save/<stem>`):
- All accept `{"overrides": {name: value}}` POST bodies
- Run writes a draft, executes it; Save writes directly to the source; Revert deletes the draft and re-runs the original

**Frontend (Three.js via importmap from CDN)**:
- `_VIEWER_JS` — ES module string injected directly into the detail page `<script type="module">` block
- Measurement tool: raycasting on the loaded STL mesh; two pins + distance line in 3D space
- Auto-reload: polls `/mtime/<stem>` every 2 seconds, reloads on change
- Dirty state / tweak bar: survives a Run → reload cycle via `sessionStorage`

## Source `.py` conventions

Parameter editing only works when CadQuery scripts follow this structure:

```python
# ============================================================
# PARAMETERS
# ============================================================
length = 724.0    # mm - plate length

# ============================================================
# MODEL
# ============================================================
```

- Section runs from `# PARAMETERS` to the next `# ===` banner
- One `name = value  # note` assignment per line
- Values with `(`, `[`, or `{` are shown read-only (treated as derived/complex)

## Installation layout

| Path | Purpose |
|---|---|
| `~/.claude/tools/stl-viewer.py` | Canonical viewer copy (read by `/stl-viewer` command) |
| `~/.claude/commands/stl-viewer.md` | Slash command definition |
| `~/.claude/skills/parametric-3d-printing/` | Optional CadQuery skill (generates `.py`, `.stl`, `_preview.png`) |
