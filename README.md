# HospitalSim

An agent-based hospital infection simulation built with Mesa and Solara.

---

## Requirements

- Python 3.9+
- Install dependencies:

```bash
pip install mesa solara
```

---

## How to Run

1. Download all project files, keeping the folder structure intact
2. Open a terminal and navigate to the `simulation/` folder
3. Run:

```bash
python run.py
```

4. A browser window will open automatically at `http://localhost:8765`

---

## Folder Structure

```
project/
│
├── public/
│   └── floorplaneditor.html    ← Fabric.js floor plan editor (open in browser to draw custom layouts)
│
└── simulation/
    ├── run.py                  ← Entry point — start here
    ├── app.py                  ← Solara app root and page routing
    ├── state.py                ← Shared reactive state across all pages
    ├── ui.py                   ← Shared UI components and colour palette
    │
    ├── model.py                ← Simulation engine and Wells-Riley infection model
    ├── agents.py               ← Agent behaviour and movement (FSM per role)
    ├── floorplan.py            ← Floor plan geometry, A* pathfinding, predefined layouts
    ├── persistence.py          ← Saving, loading, and CSV export of results
    │
    ├── home.py                 ← Home / landing page
    ├── settings_fp.py          ← Step 1: floor plan selection and upload
    ├── settings_params.py      ← Step 2: parameter sliders and model launch
    ├── simulation.py           ← Live simulation view with real-time SVG rendering
    ├── analytics.py            ← Post-run results, charts, and heatmap
    ├── previous.py             ← Saved runs browser
    │
    ├── Test.py                 ← Unit, integration, validation, and boundary tests
    └── README.md
```

---

## Custom Floor Plans

1. Open `public/floorplaneditor.html` in a browser
2. Draw your hospital layout using the Fabric.js interface
3. Export as JSON
4. On the Floor Plan settings page, drag and drop the exported JSON file to use it in the simulation

---

## Notes

- Saved runs are stored in `~/.hospitalsim/results/`
- CSV exports are saved to `~/.hospitalsim/results/exports/`
- To run the test suite: `python -m pytest Test.py`
