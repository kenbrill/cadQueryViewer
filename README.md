# CadQuery STL Viewer

A local web viewer for parametric 3D models built with [CadQuery](https://cadquery.readthedocs.io/). Drop `viewer.py` into any directory that contains `.stl` files and get an interactive browser-based viewer with:

- Card grid index of all STLs with preview thumbnails and watertight badges
- Interactive 3D WebGL viewer (orbit, zoom, pan)
- Live coordinate readout and two-point distance measurement
- Editable parameter table — change a value, click **Run**, see the model rebuild in-place
- **Save** / **Revert** buttons to commit or discard tweaks
- Auto-reload when any STL or source `.py` changes on disk
- Resizable sidebar, axis orientation arrows
- **Assembly View** — load all STLs at once to check how parts fit together

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10 – 3.12 | 3.13+ lacks CadQuery OCC wheels |
| AI coding assistant | any | Claude Code, Cursor, Copilot, or any agentic AI tool |
| CadQuery skill | — | optional — see Step 1 |

---

## Installation

### Step 1 — Install the parametric-3d-printing skill *(optional)*

**This step is optional.** You can use the viewer with any CadQuery script you write by hand, or with a different AI skill or workflow that generates CadQuery code.

That said, this viewer was built alongside the [flowful-ai/cad-skill](https://github.com/flowful-ai/cad-skill) agentic AI skill, which is what generates the `.py` files, STL exports, and preview PNGs that the viewer is designed to read. If you use that skill, everything works together out of the box — the `# PARAMETERS` section structure, the export naming conventions, and the preview PNG naming all match what the viewer expects.

If you write CadQuery scripts by hand or use a different tool, the viewer can still display your STLs in 3D and show measurement data — but the **parameter table** (and the Run / Save / Revert editing workflow) only works if your `.py` files follow the conventions described in the [Source `.py` requirements](#source-py-requirements) section below. Code structured differently — different section headers, parameters defined as class attributes, config files, etc. — won't be parsed correctly.

To install the skill:

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/flowful-ai/cad-skill ~/.claude/skills/parametric-3d-printing
```

> Source: [flowful-ai/cad-skill](https://github.com/flowful-ai/cad-skill) — PolyForm Noncommercial License

### Step 2 — Install the `/stl-viewer` slash command *(Claude Code)*

This step is specific to [Claude Code](https://claude.ai/code). If you use a different AI coding assistant, check whether it supports custom slash commands or similar plugin mechanisms — the concept translates, but the file location and format will differ.

Copy the slash command into your Claude Code commands directory so `/stl-viewer` is available in any project:

```bash
mkdir -p ~/.claude/commands
cp stl-viewer.md ~/.claude/commands/stl-viewer.md
```

### Step 3 — Store the canonical viewer

The slash command pulls `viewer.py` from a fixed location. Put it there:

```bash
mkdir -p ~/.claude/tools
cp viewer.py ~/.claude/tools/stl-viewer.py
```

### Step 4 — Install Python dependencies

In each project directory you use the viewer in, create a virtual environment and install:

```bash
python3.12 -m venv .venv
.venv/bin/pip install flask trimesh cadquery pyrender Pillow
```

- `flask` — required for the viewer server
- `trimesh` — enables watertight mesh badges
- `cadquery`, `pyrender`, `Pillow` — required for the CadQuery skill (model building + preview rendering)

---

## Usage

### Starting the viewer

**With Claude Code** — type in any session inside a directory with `.stl` files:

```
/stl-viewer
```

- If `viewer.py` is **not** present → copies it in, installs Flask, starts the server, opens the browser
- If `viewer.py` is **already** present → stops the server and removes `viewer.py`

**With any other AI tool, or manually** — just run the script directly:

```bash
.venv/bin/python viewer.py
```

The viewer auto-detects a free port (starting at 7173) and opens `http://localhost:<port>` automatically.

### Workflow with CadQuery

1. Ask your AI coding assistant to design a model. It will create a `.py` script with a `# PARAMETERS` section and export one or more `.stl` files.
2. If using the CadQuery skill, it also renders a `_preview.png` for each STL.
3. Start the viewer (via `/stl-viewer` in Claude Code, or `python viewer.py` directly) to browse the results. Click any card to open the 3D view.
4. To tweak a value — click the number in the **Parameters** column, type a new value. The field highlights yellow.
5. Click **▶ Run** — a spinner appears while CadQuery rebuilds; the 3D model reloads automatically.
6. Click **Save** to write the new values back into the source `.py`. Click **Revert** to restore the original.

### Measurement tool

- **Hover** over the model — X/Y/Z coordinates appear in the top-right HUD (in CadQuery model space).
- **Click** once — drops a yellow pin (Pin A).
- **Click** again — drops an orange pin (Pin B), draws a line, shows ΔX/ΔY/ΔZ and total distance in mm.
- **Click** a third time or press **Escape** to reset.

This lets you tell your AI assistant things like "the hook back wall is at Y=46.5 — move it 5mm in +Y."

### Assembly View

When 2 or more STLs exist, an **Assembly View** button appears on the index page. It loads all parts simultaneously in distinct colors at their native CadQuery coordinates — so parts designed in a shared coordinate space appear assembled by default.

**Selecting and moving parts**

- **Click** any part in the viewport — colored drag handles appear on it.
- Press **T** to switch to translate handles (arrows along each axis).
- Press **R** to switch to rotate handles (arcs around each axis).
- Drag a handle to move or spin the part with the mouse.
- Press **Escape** to deselect (hide the handles).

**Sidebar controls**

Each part has a card in the right sidebar with number inputs for precise X/Y/Z translate and rotate offsets. Typing a value moves the part immediately; drag-and-drop and number inputs stay in sync.

- The **eye icon** toggles a part's visibility — useful for inspecting internal geometry without deleting the part from the scene.
- **Reset** zeros all offsets for that part and snaps it back to its original position.

The Assembly View has no Run/Save workflow — it is a visual check tool only. Changes are not written back to any file.

---

## Source `.py` requirements

For parameters to appear in the viewer sidebar, your CadQuery script must have a `# PARAMETERS` section like this:

```python
import cadquery as cq

# ============================================================
# PARAMETERS
# ============================================================
length = 724.0    # mm - plate length
width  = 140.0    # mm - plate width
thick  =   6.0    # mm - plate thickness

# ============================================================
# MODEL
# ============================================================
result = cq.Workplane("XY").box(length, width, thick, centered=(True, True, False))

# ============================================================
# EXPORT
# ============================================================
cq.exporters.export(result, "my_model.stl", tolerance=0.01, angularTolerance=0.1)
```

Rules:
- Section starts at `# PARAMETERS`, ends at the next `# ===` banner or section header
- One assignment per line: `name = value  # optional note`
- Values containing `(`, `[`, or `{` are treated as derived/complex and shown read-only

---

## Files in this package

| File | Purpose |
|---|---|
| `viewer.py` | Self-contained Flask viewer — drop into any STL directory |
| `stl-viewer.md` | Claude Code slash command definition (`/stl-viewer`) — adapt for other AI tools as needed |
| `README.md` | This file |
