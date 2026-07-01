#!/usr/bin/env python3
"""
STL model viewer — drop viewer.py into any directory with .stl files and run:
    python viewer.py          (or: .venv/bin/python viewer.py)
Requires: pip install flask
Optional: pip install trimesh   (enables watertight badge)
"""
import os
import re
import socket
import subprocess
import sys
import webbrowser
from pathlib import Path
from threading import Timer

try:
    from flask import Flask, abort, jsonify, request, send_file
except ImportError:
    print("\n  Flask not found. Install it with:  pip install flask\n")
    raise SystemExit(1)

HERE = Path(__file__).parent
app = Flask(__name__)
_wt_cache = {}

# ── helpers ────────────────────────────────────────────────────────────────────

def all_stls():
    return sorted(HERE.glob("*.stl"))

def find_preview(stem):
    """Return the first PNG associated with this stem, or None.
    Tries: <stem>_preview.png, <stem>.png, then any <stem>*.png."""
    for candidate in [HERE / f"{stem}_preview.png", HERE / f"{stem}.png"]:
        if candidate.exists():
            return candidate
    matches = sorted(HERE.glob(f"{stem}*.png"))
    return matches[0] if matches else None

def find_source_py(stem):
    """Return the .py that generates this STL, or None."""
    direct = HERE / f"{stem}.py"
    if direct.exists():
        return direct
    py_files = [p for p in sorted(HERE.glob("*.py")) if p.name != "viewer.py"]
    # Exact literal match (e.g. export(p, "cover_plate.stl"))
    for py in py_files:
        try:
            if re.search(rf'''["']{re.escape(stem)}\.stl["']''', py.read_text()):
                return py
        except Exception:
            pass
    # Prefix match for dynamically-named exports (e.g. f"cover_piece_{i}.stl")
    prefix = re.sub(r'_\d+$', '', stem)
    if prefix != stem:
        for py in py_files:
            try:
                if prefix in py.read_text():
                    return py
            except Exception:
                pass
    return None

def parse_params(py_path):
    """Extract {name, value, note} rows from the # PARAMETERS section."""
    lines = Path(py_path).read_text().split("\n")
    start = None
    for i, line in enumerate(lines):
        if re.search(r"#\s*PARAMETERS", line):
            start = i + 1
            break
    if start is None:
        return []
    # Skip the closing banner line that immediately follows # PARAMETERS
    while start < len(lines) and re.match(r"\s*#\s*={3,}", lines[start]):
        start += 1
    params = []
    for line in lines[start:]:
        if re.match(r"\s*#\s*={3,}", line) or re.search(
            r"#\s*(MODEL|BUILD|SPLIT|EXPORT|MORTISE|CONNECTOR)", line
        ):
            break
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = re.match(r"^(\w+)\s*=\s*([^#\n]+?)(?:\s*#\s*(.*))?$", stripped)
        if not m:
            continue
        name, value, note = m.group(1), m.group(2).strip(), m.group(3) or ""
        if "(" in value or value.startswith("[") or value.startswith("{"):
            continue
        params.append({"name": name, "value": value, "note": note})
    return params

def watertight(stl_path):
    key = str(stl_path)
    if key not in _wt_cache:
        try:
            import trimesh
            _wt_cache[key] = trimesh.load(key).is_watertight
        except Exception:
            _wt_cache[key] = None
    return _wt_cache[key]

def free_port(start=7173):
    for port in range(start, start + 20):
        with socket.socket() as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    return start

def patch_params(text, overrides):
    for name, val in overrides.items():
        text = re.sub(
            rf'^(\s*{re.escape(name)}\s*=\s*)[^#\n]+(.*)',
            rf'\g<1>{val}\2',
            text, count=1, flags=re.MULTILINE
        )
    return text

def run_script(py_path):
    venv_py = HERE / '.venv/bin/python'
    python  = str(venv_py) if venv_py.exists() else sys.executable
    try:
        r = subprocess.run(
            [python, str(py_path)], cwd=str(HERE),
            capture_output=True, text=True, timeout=180
        )
        return {'ok': r.returncode == 0, 'stdout': r.stdout, 'stderr': r.stderr}
    except subprocess.TimeoutExpired:
        return {'ok': False, 'stdout': '', 'stderr': 'Timed out after 180 s'}

# ── shared styles ──────────────────────────────────────────────────────────────

SHARED_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, sans-serif; background: #0f0f1a; color: #e0e0e0; }
a { color: #7ab3ef; text-decoration: none; }
a:hover { text-decoration: underline; }
header { background: #16213e; padding: .9rem 1.5rem; border-bottom: 1px solid #252545;
         display: flex; align-items: baseline; gap: 1rem; flex-wrap: wrap; }
header h1 { font-size: 1rem; font-weight: 600; color: #c0d0f0; }
header .sub { font-size: .78rem; color: #4a5070; }
.badge { display:inline-block; padding:2px 8px; border-radius:10px;
         font-size:.7rem; font-weight:600; }
.ok  { background:#1a4a2a; color:#5de07a; }
.bad { background:#4a1a1a; color:#e05d5d; }
.unk { background:#222; color:#666; }
"""

# ── index page ─────────────────────────────────────────────────────────────────

INDEX_CSS = """
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(210px,1fr));
        gap:1.2rem; padding:1.5rem; }
.card { background:#16213e; border:1px solid #252545; border-radius:8px;
        overflow:hidden; transition:transform .15s, box-shadow .15s; }
.card:hover { transform:translateY(-3px); box-shadow:0 6px 20px rgba(0,0,0,.5); }
.thumb { width:100%; height:130px; object-fit:cover; background:#0a0a14; display:block; }
.thumb-ph { width:100%; height:130px; background:#0a0a14;
            display:flex; align-items:center; justify-content:center;
            color:#1e1e38; font-size:3rem; }
.card-body { padding:.75rem; }
.card-body h3 { font-size:.88rem; color:#c0d0f0; margin-bottom:.4rem;
                white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.card-meta { font-size:.72rem; color:#445; display:flex;
             justify-content:space-between; align-items:center; }
.assembly-btn { font-size:.78rem; padding:3px 14px; background:#1a2a3a; color:#7ab3ef;
                border:1px solid #2a3a5a; border-radius:4px; margin-left:auto;
                align-self:center; }
.assembly-btn:hover { background:#253a5a; text-decoration:none; }
"""

def index_page(stls):
    if not stls:
        body = "<p style='padding:2rem;color:#446'>No .stl files found in this directory.</p>"
    else:
        cards = ""
        for stl in stls:
            stem = stl.stem
            size_kb = stl.stat().st_size // 1024
            wt = watertight(stl)
            bcls = "ok" if wt is True else ("bad" if wt is False else "unk")
            btxt = "Watertight" if wt is True else ("Not watertight" if wt is False else "?")
            pv = find_preview(stem)
            thumb = (f'<img class="thumb" src="/files/img/{pv.name}" alt="{stem}">'
                     if pv else '<div class="thumb-ph">&#9651;</div>')
            cards += f"""
        <a href="/model/{stem}">
          <div class="card">
            {thumb}
            <div class="card-body">
              <h3>{stem}</h3>
              <div class="card-meta">
                <span>{size_kb} KB</span>
                <span class="badge {bcls}">{btxt}</span>
              </div>
            </div>
          </div>
        </a>"""
        body = f'<div class="grid">{cards}</div>'

    assembly_btn = ('<a class="assembly-btn" href="/assembly">Assembly View</a>'
                    if len(stls) >= 2 else '')
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>STL Models</title>
<style>{SHARED_CSS}{INDEX_CSS}</style></head>
<body>
<header><h1>STL Models</h1><span class="sub">{HERE}</span>{assembly_btn}</header>
{body}
</body></html>"""

# ── detail page ────────────────────────────────────────────────────────────────

DETAIL_CSS = """
.layout { display:flex; height:calc(100vh - 48px); }
#viewerWrap { flex:1; position:relative; min-width:0; background:#080810; }
#viewer { width:100%; height:100%; display:block; }
#coordHud { position:absolute; top:12px; right:14px; background:rgba(8,8,24,.88);
            color:#c0d0f0; font:12px/1.8 monospace; padding:8px 12px; border-radius:6px;
            border:1px solid #252545; pointer-events:none; display:none; min-width:190px; }
.hud-hover { color:#7ab3ef; }
.hud-label { color:#6677aa; font-size:.68rem; text-transform:uppercase;
             letter-spacing:.06em; margin-top:5px; }
.hud-dist { color:#ffdd44; font-size:1.05em; font-weight:700; margin-top:3px; }
.hud-hint { color:#4a5070; font-size:.72rem; margin-top:4px; }
.resize-handle { width:5px; flex-shrink:0; background:#1a1a30; cursor:col-resize;
                 transition:background .15s; }
.resize-handle:hover, .resize-handle.dragging { background:#4a5080; }
.sidebar { width:340px; flex-shrink:0; display:flex; flex-direction:column;
           background:#111120; min-width:180px; max-width:800px; }
.params-area { flex:1; min-height:0; overflow-y:auto; padding:1rem; }
.preview-area { flex-shrink:0; padding:.75rem 1rem 1rem;
                border-top:1px solid #1a1a30; }
.back { font-size:.78rem; color:#7ab3ef; display:block; margin-bottom:.8rem; }
.sidebar h2 { font-size:.95rem; color:#c0d0f0; margin-bottom:.2rem; }
.section-title { font-size:.7rem; color:#6677aa; text-transform:uppercase;
                 letter-spacing:.06em; margin:1rem 0 .35rem; }
table { width:100%; border-collapse:collapse; font-size:.78rem; }
td { padding:3px 5px; border-bottom:1px solid #1a1a30; vertical-align:top; }
td:first-child { color:#7ab3ef; font-family:monospace; white-space:nowrap; padding-right:8px; }
td:nth-child(2) { color:#e0e0e0; font-family:monospace; }
td:last-child { color:#556; font-size:.72rem; }
.src-link { margin-top:.8rem; font-size:.78rem; }
.param-input { background:transparent; border:none; border-bottom:1px solid transparent;
               color:#e0e0e0; font-family:monospace; font-size:.78rem;
               width:100%; padding:0; outline:none; cursor:text; }
.param-input:focus { border-bottom-color:#7ab3ef; }
.param-input.dirty { color:#ffdd44; border-bottom-color:#ffdd44; }
#tweakBar { display:none; align-items:center; gap:.5rem; margin-left:auto; }
#runStatus { font-size:.72rem; color:#6677aa; min-width:5rem; text-align:right; }
.hdr-btn { padding:3px 12px; border-radius:4px; border:none; cursor:pointer;
           font-size:.78rem; font-weight:600; }
.hdr-btn:disabled { opacity:.45; cursor:default; }
.btn-revert { background:#2a1a1a; color:#e05d5d; }
.btn-run    { background:#1a4a2a; color:#5de07a; }
.btn-save   { background:#1a2a4a; color:#7ab3ef; }
#buildOverlay { display:none; position:fixed; inset:0; z-index:999;
                background:rgba(8,8,20,.78); backdrop-filter:blur(3px);
                flex-direction:column; align-items:center; justify-content:center;
                gap:1.4rem; }
#buildOverlay.active { display:flex; }
.spinner { width:56px; height:56px; border-radius:50%;
           border:5px solid #252545; border-top-color:#5de07a;
           animation:spin .9s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }
#buildMsg { color:#c0d0f0; font-size:.95rem; font-family:monospace;
            letter-spacing:.05em; }
.preview-label { font-size:.7rem; color:#6677aa; text-transform:uppercase;
                 letter-spacing:.06em; margin-bottom:.35rem; }
.preview-ph { width:100%; aspect-ratio:4/3; background:#0a0a14; border-radius:4px;
              border:1px solid #1a1a30; display:flex; align-items:center;
              justify-content:center; color:#1e1e38; font-size:2.5rem; }
.preview-img { width:100%; border-radius:4px; border:1px solid #252545; display:block; }
"""

_VIEWER_JS = r"""
import * as THREE from 'three';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const canvas = document.getElementById('viewer');
const hud    = document.getElementById('coordHud');
const W = () => canvas.clientWidth, H = () => canvas.clientHeight;

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(W(), H());
renderer.setClearColor(0x080810);

const scene  = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(45, W() / H(), 0.1, 500000);

scene.add(new THREE.AmbientLight(0xffffff, 0.5));
const sun = new THREE.DirectionalLight(0xffffff, 0.9); sun.position.set(3, 5, 4); scene.add(sun);
const fill = new THREE.DirectionalLight(0x8899ff, 0.3); fill.position.set(-3,-2,-2); scene.add(fill);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true; controls.dampingFactor = 0.07;

// ── HUD helpers ───────────────────────────────────────────────
const f   = v => v.toFixed(1);
const fpt = p => `X:&nbsp;${f(p.x)}&ensp;Y:&nbsp;${f(p.y)}&ensp;Z:&nbsp;${f(p.z)}`;

function renderHud(hover, pins) {
    if (!hover && !pins.length) { hud.style.display = 'none'; return; }
    hud.style.display = 'block';
    let h = hover ? `<div class="hud-hover">${fpt(hover)}</div>` : '';
    if (pins.length >= 1)
        h += `<div class="hud-label">Pin A</div><div>${fpt(pins[0].cq)}</div>`;
    if (pins.length >= 2) {
        const dx = pins[1].cq.x-pins[0].cq.x, dy = pins[1].cq.y-pins[0].cq.y, dz = pins[1].cq.z-pins[0].cq.z;
        h += `<div class="hud-label">Pin B</div><div>${fpt(pins[1].cq)}</div>`;
        h += `<div class="hud-label">Delta</div>`;
        h += `<div>ΔX:&nbsp;${f(dx)}&ensp;ΔY:&nbsp;${f(dy)}&ensp;ΔZ:&nbsp;${f(dz)}</div>`;
        h += `<div class="hud-dist">&#8596;&nbsp;${f(Math.sqrt(dx*dx+dy*dy+dz*dz))} mm</div>`;
        h += `<div class="hud-hint">Esc or click to reset</div>`;
    } else if (pins.length === 1) {
        h += `<div class="hud-hint">Click second point to measure</div>`;
    }
    hud.innerHTML = h;
}

// ── Measurement state ─────────────────────────────────────────
const raycaster = new THREE.Raycaster();
const mouse     = new THREE.Vector2();
let loadedMesh  = null, modelCenter = new THREE.Vector3(), pinR = 1;
let hoverPt = null, pins = [], pinMarkers = [], measureLine = null;

const wToCq = w => new THREE.Vector3(w.x+modelCenter.x, w.y+modelCenter.y, w.z+modelCenter.z);

function makePin(wp, color) {
    const m = new THREE.Mesh(
        new THREE.SphereGeometry(pinR, 12, 8),
        new THREE.MeshBasicMaterial({ color, depthTest: false })
    );
    m.position.copy(wp); scene.add(m); return m;
}

function clearPins() {
    pinMarkers.forEach(m => scene.remove(m)); pinMarkers = []; pins = [];
    if (measureLine) { scene.remove(measureLine); measureLine = null; }
}

function drawLine(a, b) {
    if (measureLine) scene.remove(measureLine);
    measureLine = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([a, b]),
        new THREE.LineBasicMaterial({ color: 0xffffff, depthTest: false })
    );
    scene.add(measureLine);
}

function castRay(e) {
    const r = canvas.getBoundingClientRect();
    mouse.x =  ((e.clientX - r.left) / r.width)  * 2 - 1;
    mouse.y = -((e.clientY - r.top)  / r.height)  * 2 + 1;
    raycaster.setFromCamera(mouse, camera);
    const hits = loadedMesh ? raycaster.intersectObject(loadedMesh) : [];
    return hits.length ? hits[0].point.clone() : null;
}

canvas.addEventListener('mousemove', e => {
    const wp = castRay(e);
    hoverPt = wp ? wToCq(wp) : null;
    renderHud(hoverPt, pins);
});
canvas.addEventListener('mouseleave', () => { hoverPt = null; renderHud(null, pins); });

let downAt = null;
canvas.addEventListener('mousedown', e => { downAt = { x: e.clientX, y: e.clientY }; });
canvas.addEventListener('mouseup', e => {
    if (!downAt) return;
    const dx = e.clientX - downAt.x, dy = e.clientY - downAt.y;
    downAt = null;
    if (Math.sqrt(dx*dx+dy*dy) > 4) return;

    if (pins.length >= 2) { clearPins(); renderHud(hoverPt, pins); return; }
    const wp = castRay(e);
    if (!wp) return;
    pinMarkers.push(makePin(wp, pins.length === 0 ? 0xffdd44 : 0xff8844));
    pins.push({ world: wp, cq: wToCq(wp) });
    if (pins.length === 2) drawLine(pins[0].world, pins[1].world);
    renderHud(hoverPt, pins);
});

window.addEventListener('keydown', e => {
    if (e.key === 'Escape') { clearPins(); renderHud(hoverPt, pins); }
});

// ── Axis label sprite ─────────────────────────────────────────
function makeAxisLabel(text, color) {
    const c = document.createElement('canvas'); c.width = 128; c.height = 128;
    const ctx = c.getContext('2d');
    ctx.font = 'bold 80px system-ui, sans-serif';
    ctx.fillStyle = color; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.shadowColor = 'rgba(0,0,0,0.8)'; ctx.shadowBlur = 8;
    ctx.fillText(text, 64, 64);
    return new THREE.Sprite(new THREE.SpriteMaterial({
        map: new THREE.CanvasTexture(c), transparent: true, depthTest: false
    }));
}

// ── Load model ────────────────────────────────────────────────
new STLLoader().load(STL_URL, (geo) => {
    geo.computeVertexNormals();
    const mesh = new THREE.Mesh(geo, new THREE.MeshPhongMaterial({
        color: 0x7aaabf, specular: 0x334455, shininess: 35, side: THREE.DoubleSide
    }));
    scene.add(mesh); loadedMesh = mesh;

    geo.computeBoundingBox();
    const center = new THREE.Vector3(); geo.boundingBox.getCenter(center);
    const size   = new THREE.Vector3(); geo.boundingBox.getSize(size);
    const d = Math.max(size.x, size.y, size.z);
    modelCenter.copy(center); pinR = d * 0.008;

    mesh.position.sub(center);
    camera.position.set(d*0.9, d*0.6, d*1.3);
    camera.lookAt(0,0,0); controls.target.set(0,0,0); controls.update();

    // Axis arrows at bottom-front-left corner
    const floorZ  = geo.boundingBox.min.z - center.z;
    const cornerX = geo.boundingBox.min.x - center.x;
    const cornerY = geo.boundingBox.min.y - center.y;
    const origin  = new THREE.Vector3(cornerX, cornerY, floorZ);
    const len = d*0.10, hLen = len*0.22, hW = hLen*0.65, lS = len*0.55;

    for (const [dir, col, lbl, lclr, lx, ly, lz] of [
        [new THREE.Vector3(1,0,0), 0xff4444, 'X', '#ff6666', cornerX+len*1.2, cornerY,         floorZ       ],
        [new THREE.Vector3(0,1,0), 0x44cc44, 'Y', '#44ee44', cornerX,         cornerY+len*1.2, floorZ       ],
        [new THREE.Vector3(0,0,1), 0x4488ff, 'Z', '#66aaff', cornerX,         cornerY,         floorZ+len*1.2],
    ]) {
        scene.add(new THREE.ArrowHelper(dir, origin, len, col, hLen, hW));
        const sp = makeAxisLabel(lbl, lclr);
        sp.position.set(lx, ly, lz); sp.scale.set(lS, lS, 1); scene.add(sp);
    }
});

(function animate() { requestAnimationFrame(animate); controls.update(); renderer.render(scene, camera); })();

window.addEventListener('resize', () => {
    camera.aspect = W() / H(); camera.updateProjectionMatrix(); renderer.setSize(W(), H());
});
"""

def detail_page(stem, stl_path):
    src_py  = find_source_py(stem)
    params  = parse_params(src_py) if src_py else []
    preview = find_preview(stem)
    wt      = watertight(stl_path)
    size_kb = stl_path.stat().st_size // 1024
    bcls = "ok" if wt is True else ("bad" if wt is False else "unk")
    btxt = "Watertight" if wt is True else ("Not watertight" if wt is False else "?")

    rows = "".join(
        f'<tr><td>{p["name"]}</td>'
        f'<td><input class="param-input" data-name="{p["name"]}" '
        f'data-orig="{p["value"]}" value="{p["value"]}"></td>'
        f'<td>{p["note"]}</td></tr>'
        for p in params
    ) or "<tr><td colspan='3' style='color:#446;font-style:italic'>none found</td></tr>"

    src_link = (f'<div class="src-link">'
                f'<a href="#" onclick="fetch(\'/api/edit/{stem}\');return false;">'
                f'Open: {src_py.name}</a></div>') if src_py else ""

    preview_html = (f'<img class="preview-img" src="/files/img/{preview.name}" alt="preview">'
                    if preview else '<div class="preview-ph">&#9651;</div>')

    import json as _json
    stl_url  = f"/files/stl/{stl_path.name}"
    stem_json = _json.dumps(stem)
    js = _VIEWER_JS.replace("STL_URL", f'"{stl_url}"')
    importmap = ('{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0'
                 '/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net'
                 '/npm/three@0.160.0/examples/jsm/"}}')

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>{stem}</title>
<script type="importmap">{importmap}</script>
<style>{SHARED_CSS}{DETAIL_CSS}</style></head>
<body>
<header>
  <a class="back" href="/">&#8592; All models</a>
  <h1>{stem}.stl</h1>
  <span class="sub">{size_kb} KB</span>
  <span class="badge {bcls}">{btxt}</span>
  <div id="tweakBar">
    <span id="runStatus"></span>
    <button class="hdr-btn btn-revert" id="btnRevert">Revert</button>
    <button class="hdr-btn btn-run"    id="btnRun">&#9654; Run</button>
    <button class="hdr-btn btn-save"   id="btnSave">Save</button>
  </div>
</header>
<div class="layout">
  <div id="viewerWrap">
    <canvas id="viewer"></canvas>
    <div id="coordHud"></div>
  </div>
  <div class="resize-handle" id="resizeHandle"></div>
  <div class="sidebar" id="sidebar">
    <div class="params-area">
      <h2>{stem}</h2>
      <div class="section-title">Parameters</div>
      <table>{rows}</table>
      {src_link}
    </div>
    <div class="preview-area">
      <div class="preview-label">Preview</div>
      {preview_html}
    </div>
  </div>
</div>
<div id="buildOverlay"><div class="spinner"></div><div id="buildMsg">Building model…</div></div>
<script type="module">{js}</script>
<script>
(function(){{
  const handle  = document.getElementById('resizeHandle');
  const sidebar = document.getElementById('sidebar');
  let startX, startW;
  handle.addEventListener('mousedown', e => {{
    startX = e.clientX;
    startW = sidebar.offsetWidth;
    handle.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    const onMove = e => {{
      const w = Math.max(180, Math.min(800, startW - (e.clientX - startX)));
      sidebar.style.width = w + 'px';
    }};
    const onUp = () => {{
      handle.classList.remove('dragging');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    }};
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    e.preventDefault();
  }});
}})();
</script>
<script>
(function(){{
  const stem = {stem_json};
  let known = null;
  async function poll(){{
    try {{
      const r = await fetch('/mtime/' + stem);
      if (!r.ok) return;
      const {{ mtime }} = await r.json();
      if (known === null) {{ known = mtime; return; }}
      if (mtime !== known) {{
        const bar = document.getElementById('tweakBar');
        if (bar && bar.style.display !== 'none') {{
          const ov = {{}};
          document.querySelectorAll('.param-input').forEach(el => {{
            if (el.value !== el.dataset.orig) ov[el.dataset.name] = el.value;
          }});
          sessionStorage.setItem('tweak_' + stem, JSON.stringify(ov));
        }}
        location.reload();
      }}
    }} catch(e) {{}}
  }}
  poll();
  setInterval(poll, 2000);
}})();
</script>
<script>
(function(){{
  const stem     = {stem_json};
  const inputs   = Array.from(document.querySelectorAll('.param-input'));
  const tweakBar = document.getElementById('tweakBar');
  const btnRun   = document.getElementById('btnRun');
  const btnRevert= document.getElementById('btnRevert');
  const btnSave  = document.getElementById('btnSave');
  const status   = document.getElementById('runStatus');
  const overlay  = document.getElementById('buildOverlay');
  const buildMsg = document.getElementById('buildMsg');

  // Track what the displayed model was last built with so the bar stays
  // visible even if the user types back to the original value.
  let displayedOverrides = JSON.parse(sessionStorage.getItem('model_built_' + stem) || '{{}}');

  function getOverrides() {{
    const o = {{}};
    inputs.forEach(el => {{ if (el.value !== el.dataset.orig) o[el.dataset.name] = el.value; }});
    return o;
  }}

  function modelIsStale() {{
    return inputs.some(el => {{
      const built = displayedOverrides[el.dataset.name];
      return built !== undefined && built !== el.dataset.orig;
    }});
  }}

  function updateDirty() {{
    const dirty = Object.keys(getOverrides()).length > 0;
    inputs.forEach(el => el.classList.toggle('dirty', el.value !== el.dataset.orig));
    tweakBar.style.display = (dirty || modelIsStale()) ? 'flex' : 'none';
  }}

  inputs.forEach(el => el.addEventListener('input', updateDirty));

  // Restore tweaked values that survived a Run → reload cycle
  const _saved = sessionStorage.getItem('tweak_' + stem);
  if (_saved) {{
    sessionStorage.removeItem('tweak_' + stem);
    const ov = JSON.parse(_saved);
    inputs.forEach(el => {{ if (el.dataset.name in ov) el.value = ov[el.dataset.name]; }});
    updateDirty();
  }}

  function setWorking(msg) {{
    [btnRun, btnRevert, btnSave].forEach(b => b.disabled = true);
    status.textContent = msg;
    buildMsg.textContent = msg;
    overlay.classList.add('active');
  }}

  function setIdle(msg, ok) {{
    overlay.classList.remove('active');
    [btnRun, btnRevert, btnSave].forEach(b => b.disabled = false);
    status.style.color = ok ? '#5de07a' : '#e05d5d';
    status.textContent = msg;
    setTimeout(() => {{ status.textContent = ''; status.style.color = '#6677aa'; }}, 4000);
  }}

  async function post(url, overrides) {{
    const r = await fetch(url, {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{overrides}})
    }});
    return r.json();
  }}

  btnRun.addEventListener('click', async () => {{
    setWorking('Running…');
    const overrides = getOverrides();
    const r = await post(`/api/run/${{stem}}`, overrides);
    if (r.ok) {{
      displayedOverrides = overrides;
      sessionStorage.setItem('model_built_' + stem, JSON.stringify(overrides));
      updateDirty();
    }}
    setIdle(r.ok ? '✓ Done' : '✗ Failed', r.ok);
    if (!r.ok) console.error(r.stderr);
  }});

  btnRevert.addEventListener('click', async () => {{
    setWorking('Reverting…');
    const r = await post(`/api/revert/${{stem}}`, {{}});
    if (r.ok) {{
      displayedOverrides = {{}};
      sessionStorage.removeItem('model_built_' + stem);
    }}
    inputs.forEach(el => {{ el.value = el.dataset.orig; }});
    updateDirty();
    setIdle(r.ok ? '✓ Reverted' : '✗ Failed', r.ok);
  }});

  btnSave.addEventListener('click', async () => {{
    setWorking('Saving…');
    const overrides = getOverrides();
    const r = await post(`/api/save/${{stem}}`, overrides);
    if (r.ok) {{
      displayedOverrides = {{}};
      sessionStorage.removeItem('model_built_' + stem);
      inputs.forEach(el => {{ el.dataset.orig = el.value; }});
      updateDirty();
    }}
    setIdle(r.ok ? '✓ Saved' : '✗ Failed', r.ok);
  }});
}})();
</script>
</body></html>"""

# ── assembly page ─────────────────────────────────────────────────────────────

ASSEMBLY_COLORS_CSS = [
    "#7aaabf", "#e07a5f", "#81b29a", "#f2cc8f",
    "#8ecae6", "#d4a373", "#b5838d", "#6d6875",
]

ASSEMBLY_CSS = """
.back { font-size:.78rem; }
.layout { display:flex; height:calc(100vh - 48px); }
#viewerWrap { flex:1; position:relative; min-width:0; background:#080810; }
#viewer { width:100%; height:100%; display:block; }
#coordHud { position:absolute; top:12px; right:14px; background:rgba(8,8,24,.88);
            color:#c0d0f0; font:12px/1.8 monospace; padding:8px 12px; border-radius:6px;
            border:1px solid #252545; pointer-events:none; display:none; min-width:180px; }
.hud-hover { color:#7ab3ef; }
.sidebar { width:340px; flex-shrink:0; overflow-y:auto; overflow-x:hidden;
           background:#111120; border-left:1px solid #1a1a30; }
.sidebar-hint { padding:.5rem .75rem; font-size:.68rem; color:#2a2a55;
                border-bottom:1px solid #1a1a30; }
.model-card { border-bottom:1px solid #1a1a30; padding:.75rem; transition:background .1s; }
.model-card.selected { background:#1a2030; outline:1px solid #4a6080; }
.card-hdr { display:flex; align-items:center; gap:.5rem; margin-bottom:.55rem; }
.swatch { width:11px; height:11px; border-radius:50%; flex-shrink:0; }
.card-name { flex:1; font-size:.85rem; color:#c0d0f0; font-weight:600;
             white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.vis-btn { background:none; border:none; cursor:pointer; font-size:.88rem; padding:0 2px;
           color:#7ab3ef; opacity:1; transition:opacity .15s; }
.vis-btn.vis-off { opacity:.25; }
.tf-row { display:flex; align-items:center; gap:.5rem; margin-bottom:.4rem; }
.tf-label { color:#6677aa; font-size:.65rem; text-transform:uppercase;
            letter-spacing:.04em; width:3.8rem; flex-shrink:0; }
.tf-axes { display:flex; gap:.35rem; }
.tf-axes label { display:flex; align-items:center; gap:2px; color:#556; font-size:.72rem; }
.tf-input { width:52px; background:#0a0a18; border:1px solid #252545; border-radius:3px;
            color:#e0e0e0; font-family:monospace; font-size:.73rem; padding:2px 4px;
            text-align:right; -moz-appearance:textfield; }
.tf-input::-webkit-inner-spin-button { opacity:.3; }
.tf-input:focus { outline:none; border-color:#7ab3ef; }
.reset-btn { background:#1a1a2a; border:1px solid #252545; border-radius:3px;
             color:#7ab3ef; font-size:.7rem; padding:2px 10px; cursor:pointer;
             margin-top:.35rem; }
.reset-btn:hover { background:#252545; }
"""

_ASSEMBLY_JS = r"""
import * as THREE from 'three';
import { STLLoader }        from 'three/addons/loaders/STLLoader.js';
import { OrbitControls }    from 'three/addons/controls/OrbitControls.js';
import { TransformControls } from 'three/addons/controls/TransformControls.js';

const canvas = document.getElementById('viewer');
const hud    = document.getElementById('coordHud');
const W = () => canvas.clientWidth, H = () => canvas.clientHeight;

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(W(), H());
renderer.setClearColor(0x080810);

const scene  = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(45, W() / H(), 0.1, 500000);

scene.add(new THREE.AmbientLight(0xffffff, 0.5));
const sun  = new THREE.DirectionalLight(0xffffff, 0.9); sun.position.set(3, 5, 4); scene.add(sun);
const fill = new THREE.DirectionalLight(0x8899ff, 0.3); fill.position.set(-3,-2,-2); scene.add(fill);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true; controls.dampingFactor = 0.07;

// TransformControls — pauses orbit while dragging a handle
const tc = new TransformControls(camera, renderer.domElement);
tc.setSize(0.8);
scene.add(tc);
tc.addEventListener('dragging-changed', e => { controls.enabled = !e.value; });

// When a handle is dragged, read the mesh's new transform back into state + inputs
tc.addEventListener('objectChange', () => {
    const s = state[selectedIdx];
    if (!s || !s.mesh) return;
    s.ox = s.mesh.position.x; s.oy = s.mesh.position.y; s.oz = s.mesh.position.z;
    s.rx = s.mesh.rotation.x * 180 / Math.PI;
    s.ry = s.mesh.rotation.y * 180 / Math.PI;
    s.rz = s.mesh.rotation.z * 180 / Math.PI;
    document.querySelectorAll(`.tf-input[data-idx="${selectedIdx}"]`).forEach(inp => {
        inp.value = +(s[inp.dataset.axis].toFixed(1));
    });
});

const MODELS = MODELS_JSON;
const state  = MODELS.map(m => ({ ...m, mesh: null, ox:0, oy:0, oz:0, rx:0, ry:0, rz:0 }));

let loadedCount = 0, selectedIdx = -1;
const raycaster = new THREE.Raycaster();
const mouse     = new THREE.Vector2();

function applyTransform(s) {
    if (!s.mesh) return;
    s.mesh.position.set(s.ox, s.oy, s.oz);
    s.mesh.rotation.set(s.rx * Math.PI / 180, s.ry * Math.PI / 180, s.rz * Math.PI / 180);
}

function selectModel(idx) {
    selectedIdx = idx;
    document.querySelectorAll('.model-card').forEach((el, i) => el.classList.toggle('selected', i === idx));
    if (idx >= 0 && state[idx].mesh) {
        tc.attach(state[idx].mesh);
        const card = document.querySelector(`.model-card[data-idx="${idx}"]`);
        if (card) card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } else {
        tc.detach();
    }
}

function makeAxisLabel(text, color) {
    const c = document.createElement('canvas'); c.width = 128; c.height = 128;
    const ctx = c.getContext('2d');
    ctx.font = 'bold 80px system-ui, sans-serif';
    ctx.fillStyle = color; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.shadowColor = 'rgba(0,0,0,0.8)'; ctx.shadowBlur = 8;
    ctx.fillText(text, 64, 64);
    return new THREE.Sprite(new THREE.SpriteMaterial({
        map: new THREE.CanvasTexture(c), transparent: true, depthTest: false
    }));
}

function frameAll() {
    const box = new THREE.Box3();
    state.forEach(s => { if (s.mesh) box.expandByObject(s.mesh); });
    if (box.isEmpty()) return;
    const center = new THREE.Vector3(); box.getCenter(center);
    const size   = new THREE.Vector3(); box.getSize(size);
    const d = Math.max(size.x, size.y, size.z);
    controls.target.copy(center);
    camera.position.set(center.x + d*0.9, center.y + d*0.6, center.z + d*1.3);
    camera.lookAt(center); controls.update();

    const o  = box.min.clone();
    const len = d*0.10, hLen = len*0.22, hW = hLen*0.65, lS = len*0.55;
    for (const [dir, col, lbl, lclr, lx, ly, lz] of [
        [new THREE.Vector3(1,0,0), 0xff4444, 'X', '#ff6666', o.x+len*1.2, o.y,         o.z        ],
        [new THREE.Vector3(0,1,0), 0x44cc44, 'Y', '#44ee44', o.x,         o.y+len*1.2, o.z        ],
        [new THREE.Vector3(0,0,1), 0x4488ff, 'Z', '#66aaff', o.x,         o.y,         o.z+len*1.2],
    ]) {
        scene.add(new THREE.ArrowHelper(dir, o, len, col, hLen, hW));
        const sp = makeAxisLabel(lbl, lclr);
        sp.position.set(lx, ly, lz); sp.scale.set(lS, lS, 1); scene.add(sp);
    }
}

const loader = new STLLoader();
state.forEach((s) => {
    loader.load(s.url, (geo) => {
        geo.computeVertexNormals();
        s.mesh = new THREE.Mesh(geo, new THREE.MeshPhongMaterial({
            color: s.color, specular: 0x334455, shininess: 35, side: THREE.DoubleSide
        }));
        applyTransform(s);
        scene.add(s.mesh);
        loadedCount++;
        if (loadedCount === state.length) frameAll();
    });
});

// ── HUD ───────────────────────────────────────────────────────────────────────
const fv = v => v.toFixed(1);
canvas.addEventListener('mousemove', e => {
    if (tc.dragging) { hud.style.display = 'none'; return; }
    const r = canvas.getBoundingClientRect();
    mouse.x =  ((e.clientX - r.left) / r.width)  * 2 - 1;
    mouse.y = -((e.clientY - r.top)  / r.height)  * 2 + 1;
    raycaster.setFromCamera(mouse, camera);
    const meshes = state.filter(s => s.mesh && s.mesh.visible).map(s => s.mesh);
    const hits   = raycaster.intersectObjects(meshes);
    if (hits.length) {
        const p = hits[0].point;
        hud.style.display = 'block';
        hud.innerHTML = `<div class="hud-hover">X:&nbsp;${fv(p.x)}&ensp;Y:&nbsp;${fv(p.y)}&ensp;Z:&nbsp;${fv(p.z)}</div>`;
    } else {
        hud.style.display = 'none';
    }
});
canvas.addEventListener('mouseleave', () => { hud.style.display = 'none'; });

// ── Click to select ───────────────────────────────────────────────────────────
// Only acts on actual mesh hits — clicking TC handles or empty space is ignored.
// Press Escape to deselect.
let downAt = null;
canvas.addEventListener('mousedown', e => { downAt = { x: e.clientX, y: e.clientY }; });
canvas.addEventListener('mouseup',   e => {
    if (!downAt) return;
    const dx = e.clientX - downAt.x, dy = e.clientY - downAt.y;
    downAt = null;
    if (Math.sqrt(dx*dx + dy*dy) > 4 || tc.dragging) return;

    const r = canvas.getBoundingClientRect();
    mouse.x =  ((e.clientX - r.left) / r.width)  * 2 - 1;
    mouse.y = -((e.clientY - r.top)  / r.height)  * 2 + 1;
    raycaster.setFromCamera(mouse, camera);
    const meshes = state.filter(s => s.mesh && s.mesh.visible).map(s => s.mesh);
    const hits   = raycaster.intersectObjects(meshes);
    if (!hits.length) return;
    selectModel(state.findIndex(s => s.mesh === hits[0].object));
});

// ── Keyboard ──────────────────────────────────────────────────────────────────
window.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT') return;
    if (e.key === 't' || e.key === 'T') tc.setMode('translate');
    if (e.key === 'r' || e.key === 'R') tc.setMode('rotate');
    if (e.key === 'Escape') selectModel(-1);
});

// ── Sidebar interactions ──────────────────────────────────────────────────────
document.querySelectorAll('.tf-input').forEach(el => {
    el.addEventListener('input', () => {
        const i = +el.dataset.idx, ax = el.dataset.axis;
        state[i][ax] = parseFloat(el.value) || 0;
        applyTransform(state[i]);
    });
});

document.querySelectorAll('.vis-btn').forEach(el => {
    el.addEventListener('click', () => {
        const i = +el.dataset.idx;
        if (!state[i].mesh) return;
        state[i].mesh.visible = !state[i].mesh.visible;
        el.classList.toggle('vis-off', !state[i].mesh.visible);
        if (!state[i].mesh.visible && selectedIdx === i) selectModel(-1);
    });
});

document.querySelectorAll('.reset-btn').forEach(el => {
    el.addEventListener('click', () => {
        const i = +el.dataset.idx;
        ['ox','oy','oz','rx','ry','rz'].forEach(ax => { state[i][ax] = 0; });
        document.querySelectorAll(`.tf-input[data-idx="${i}"]`).forEach(inp => { inp.value = '0'; });
        applyTransform(state[i]);
    });
});

(function animate() { requestAnimationFrame(animate); controls.update(); renderer.render(scene, camera); })();
window.addEventListener('resize', () => {
    camera.aspect = W() / H(); camera.updateProjectionMatrix(); renderer.setSize(W(), H());
});
"""

def assembly_page(stls):
    import json as _json
    cards = ""
    models_data = []
    for i, stl in enumerate(stls):
        css  = ASSEMBLY_COLORS_CSS[i % len(ASSEMBLY_COLORS_CSS)]
        col  = int(css.lstrip('#'), 16)
        models_data.append({"url": f"/files/stl/{stl.name}", "name": stl.stem,
                             "color": col, "css": css})
        cards += f"""
      <div class="model-card" data-idx="{i}">
        <div class="card-hdr">
          <span class="swatch" style="background:{css}"></span>
          <span class="card-name">{stl.stem}</span>
          <button class="vis-btn" data-idx="{i}" title="Toggle visibility">&#128065;</button>
        </div>
        <div class="tf-row">
          <span class="tf-label">Translate</span>
          <div class="tf-axes">
            <label>X<input class="tf-input" type="number" data-idx="{i}" data-axis="ox" step="1" value="0"></label>
            <label>Y<input class="tf-input" type="number" data-idx="{i}" data-axis="oy" step="1" value="0"></label>
            <label>Z<input class="tf-input" type="number" data-idx="{i}" data-axis="oz" step="1" value="0"></label>
          </div>
        </div>
        <div class="tf-row">
          <span class="tf-label">Rotate&nbsp;°</span>
          <div class="tf-axes">
            <label>X<input class="tf-input" type="number" data-idx="{i}" data-axis="rx" step="5" value="0"></label>
            <label>Y<input class="tf-input" type="number" data-idx="{i}" data-axis="ry" step="5" value="0"></label>
            <label>Z<input class="tf-input" type="number" data-idx="{i}" data-axis="rz" step="5" value="0"></label>
          </div>
        </div>
        <button class="reset-btn" data-idx="{i}">Reset</button>
      </div>"""

    models_json_str = _json.dumps(models_data)
    js = _ASSEMBLY_JS.replace("MODELS_JSON", models_json_str)
    importmap = ('{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0'
                 '/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net'
                 '/npm/three@0.160.0/examples/jsm/"}}')
    n = len(stls)
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Assembly View</title>
<script type="importmap">{importmap}</script>
<style>{SHARED_CSS}{ASSEMBLY_CSS}</style></head>
<body>
<header>
  <a class="back" href="/">&#8592; All models</a>
  <h1>Assembly View</h1>
  <span class="sub">{n} model{"s" if n != 1 else ""} &mdash; click to select &nbsp;·&nbsp; T = translate handles &nbsp;·&nbsp; R = rotate handles &nbsp;·&nbsp; Esc = deselect</span>
</header>
<div class="layout">
  <div id="viewerWrap">
    <canvas id="viewer"></canvas>
    <div id="coordHud"></div>
  </div>
  <div class="sidebar">
    {cards}
  </div>
</div>
<script type="module">{js}</script>
</body></html>"""

# ── routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return index_page(all_stls())

@app.route("/assembly")
def assembly():
    stls = all_stls()
    if len(stls) < 2:
        abort(404)
    return assembly_page(stls)

@app.route("/model/<stem>")
def model(stem):
    stl = HERE / f"{stem}.stl"
    if not stl.exists():
        abort(404)
    return detail_page(stem, stl)

@app.route("/files/stl/<filename>")
def serve_stl(filename):
    f = HERE / filename
    if not f.exists() or f.suffix != ".stl":
        abort(404)
    return send_file(f, mimetype="application/octet-stream")

@app.route("/files/img/<filename>")
def serve_img(filename):
    f = HERE / filename
    if not f.exists() or f.suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        abort(404)
    return send_file(f)

@app.route("/files/py/<filename>")
def serve_py(filename):
    f = HERE / filename
    if not f.exists() or f.suffix != ".py":
        abort(404)
    return send_file(f, mimetype="text/plain; charset=utf-8")

@app.route("/api/edit/<stem>")
def api_edit(stem):
    src = find_source_py(stem)
    if not src:
        abort(404)
    subprocess.Popen(["open", str(src)])
    return "", 204

@app.route("/api/run/<stem>", methods=["POST"])
def api_run(stem):
    src = find_source_py(stem)
    if not src: abort(404)
    overrides = request.json.get("overrides", {})
    draft = HERE / f"{src.stem}_draft.py"
    draft.write_text(patch_params(src.read_text(), overrides))
    return jsonify(run_script(draft))

@app.route("/api/revert/<stem>", methods=["POST"])
def api_revert(stem):
    src = find_source_py(stem)
    if not src: abort(404)
    draft = HERE / f"{src.stem}_draft.py"
    if draft.exists(): draft.unlink()
    return jsonify(run_script(src))

@app.route("/api/save/<stem>", methods=["POST"])
def api_save(stem):
    src = find_source_py(stem)
    if not src: abort(404)
    overrides = request.json.get("overrides", {})
    src.write_text(patch_params(src.read_text(), overrides))
    draft = HERE / f"{src.stem}_draft.py"
    if draft.exists(): draft.unlink()
    return jsonify(run_script(src))

@app.route("/mtime/<stem>")
def mtime_route(stem):
    stl = HERE / f"{stem}.stl"
    if not stl.exists():
        abort(404)
    mt = stl.stat().st_mtime
    src = find_source_py(stem)
    if src:
        mt = max(mt, src.stat().st_mtime)
    return {"mtime": mt}

# ── entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = free_port()
    url  = f"http://localhost:{port}"
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        Timer(1.2, lambda: webbrowser.open(url)).start()
        print(f"\n  STL viewer → {url}\n")
    app.run(port=port, debug=True, use_reloader=True, threaded=True)
