# Winder

A desktop GUI tool for nuclear data acquisition system cable labeling, patch panel routing, and DAQ channel mapping.

Built with Python and PyQt6. Projects are saved as `.winder` JSON files.

---

## Features

| Tab | What it does |
|---|---|
| **System Overview** | Visual rack diagram showing crates, modules, patch panels, and cables. Click-to-connect cable drawing, right-click to delete. |
| **Cables** | Sortable/filterable cable schedule table. Add, duplicate, delete, inline-edit. Auto-numbered IDs. |
| **Patch Panels** | Color-coded port grid (by signal type). Click any port to edit its label, cables, and signal type. |
| **DAQ System** | Crate → Slot → Channel tree for VME/CAMAC/NIM hardware. Right-click context menus. Saved crate templates. |
| **Signal Tracer** | Type any endpoint, port, or channel ID to trace the full signal path through the system. |

**Export:** Cable schedule, patch panel schedule, and DAQ channel list to Excel/CSV. Full system report to PDF.

---

## Installation

**Requirements:** Python 3.11+

```bash
git clone https://github.com/cbbenetti/Winder.git
cd Winder
pip install -r requirements.txt
python main.py
```

### Dependencies

```
PyQt6       — GUI framework
openpyxl    — Excel export
reportlab   — PDF export
```

---

## Quick Start

1. **File → New** — create a project, give it a name
2. **DAQ System tab** — add a crate using a template (VME 20-slot, CAMAC 25-slot, NIM 12-slot), add slots and channels
3. **Patch Panels tab** — add a panel, click ports to assign labels and signal types
4. **Cables tab** — add cables, set `From` and `To` endpoints to port IDs (e.g. `PP01-A01`) or channel IDs (e.g. `CRATE01-SL00-CH00`)
5. **System Overview tab** — see the full system; use **Connect Mode** to draw cables by clicking connectors
6. **File → Save** — saves as a `.winder` file

### Connecting cables on the overview

- Click **Connect Mode** in the toolbar (turns orange)
- Click a white connector dot on a patch panel port or DAQ channel to start
- Click a second connector to complete — a dialog lets you set cable properties
- Press **Escape** to cancel a drag
- **Right-click** any cable line to delete it

### Signal path tracing

For cables to appear as wires in the overview and in the Signal Tracer, set their `From`/`To` endpoints to exact IDs:
- Patch panel port: `PP01-A01`, `PP01-B03`, etc.
- DAQ channel: `CRATE01-SL00-CH00`, etc.
- Detector or other external endpoints (e.g. `Detector-01`) appear as labeled stubs

---

## Project Structure

```
Winder/
├── main.py                        # Entry point
├── requirements.txt
└── app/
    ├── models/
    │   ├── cable.py               # Cable dataclass
    │   ├── patch_panel.py         # PatchPanel, PatchPort dataclasses
    │   ├── daq.py                 # DaqCrate, DaqSlot, DaqChannel dataclasses
    │   └── project.py             # Top-level Project container
    ├── storage/
    │   ├── project_file.py        # Load/save .winder JSON files
    │   ├── exporter.py            # Excel, CSV, PDF export
    │   └── crate_config.py        # Saved crate templates (~/.config/winder/)
    ├── graph/
    │   └── signal_tracer.py       # BFS signal path graph engine
    └── views/
        ├── main_window.py         # QMainWindow, tab bar, menus
        ├── system_overview.py     # Interactive rack/panel/cable canvas
        ├── cable_editor.py        # Cable schedule table
        ├── patch_panel_view.py    # Port grid editor
        ├── daq_mapper.py          # Crate/slot/channel tree
        ├── signal_tracer_view.py  # Signal path query view
        └── crate_config_editor.py # Crate template manager
```

---

## Crate Templates

Built-in templates (editable via **DAQ System → Manage Templates…**):

| Template | Type | Slots |
|---|---|---|
| VME Standard | VME | 20 |
| CAMAC Standard | CAMAC | 25 |
| NIM Bin | NIM | 12 |

Templates are saved per-user at `~/.config/winder/crate_configs.json`.

---

## Data Format

Projects are stored as plain JSON with a `.winder` extension — human-readable, diff-friendly, and easy to version-control.

```json
{
  "project": { "name": "Experiment XYZ", "version": "1.0", "created": "2026-05-18" },
  "cables": [ { "id": "CBL-001", "from_endpoint": "Detector-01", "to_endpoint": "PP01-A01", ... } ],
  "patch_panels": [ { "id": "PP01", "rows": 4, "cols": 12, "ports": [ ... ] } ],
  "daq_system": { "crates": [ { "id": "CRATE01", "crate_type": "VME", "slots": [ ... ] } ] }
}
```

---

## License

MIT
