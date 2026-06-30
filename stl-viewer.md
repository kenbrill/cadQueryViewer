# STL Viewer

Toggle the local STL model viewer in the current directory.

## Steps

Run these steps using bash commands:

1. **Check if viewer is already deployed** — if `viewer.py` exists in the current directory, stop any running instance and remove it, then stop:
   ```bash
   if [ -f viewer.py ]; then
     pkill -f "python.*viewer\.py" 2>/dev/null || true
     rm viewer.py
     echo "STL viewer stopped and removed."
     exit 0
   fi
   ```
   Report to the user that the viewer was stopped and removed, then do nothing further.

2. **Copy viewer** — copy from the canonical location:
   ```bash
   cp ~/.claude/tools/stl-viewer.py viewer.py
   ```

3. **Detect Python** — use `.venv/bin/python` if a local virtualenv exists, otherwise fall back to `python3`:
   ```bash
   PYTHON=$([ -f .venv/bin/python ] && echo .venv/bin/python || echo python3)
   ```

4. **Install Flask** — install quietly:
   ```bash
   $PYTHON -m pip install flask --quiet
   ```

5. **Start the viewer** — run viewer.py and report the URL printed to stdout:
   ```bash
   $PYTHON viewer.py
   ```

   Report the URL back to the user once the server starts.
