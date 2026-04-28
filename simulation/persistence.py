from __future__ import annotations
import json
import os
import csv
import io
from typing import Dict, List, Tuple, Optional


_BASE_DIR = os.path.join(os.path.expanduser("~"), ".hospitalsim", "results")
_RUNS_DIR = os.path.join(_BASE_DIR, "runs")
_FP_DIR   = os.path.join(_BASE_DIR, "floorplans")
_INDEX    = os.path.join(_BASE_DIR, "index.json")


def _ensure_dirs():
    
    os.makedirs(_RUNS_DIR, exist_ok=True)
    os.makedirs(_FP_DIR,   exist_ok=True)


def _read_index() -> List[Dict]:
    
    if not os.path.exists(_INDEX):
        return []
    try:
        with open(_INDEX, "r") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        
        return []


def _write_index(entries: List[Dict]):
    
    _ensure_dirs()
    tmp = _INDEX + ".tmp"
    with open(tmp, "w") as f:
        json.dump(entries, f, indent=2)
    os.replace(tmp, _INDEX)


def _run_path(run_id: str) -> str:
    return os.path.join(_RUNS_DIR, f"{run_id}.json")


def _fp_path(run_id: str) -> str:
    return os.path.join(_FP_DIR, f"{run_id}.json")


def save_run(result: Dict, floor_plan=None) -> str:

    _ensure_dirs()
    run_id = result.get("id")
    if not run_id:
        raise ValueError("save_run requires result['id'] to be set")

    with open(_run_path(run_id), "w") as f:
        json.dump(result, f, indent=2, default=str)

    if floor_plan is not None:
        try:
            fp_dict = floor_plan.to_dict()
            with open(_fp_path(run_id), "w") as f:
                json.dump(fp_dict, f, indent=2)
        except Exception:
            pass

    entries = _read_index()
    
    found = False
    meta = _make_index_entry(result)
    for i, e in enumerate(entries):
        if e.get("id") == run_id:
            entries[i] = meta
            found = True
            break
    if not found:
        entries.append(meta)
    _write_index(entries)
    return run_id


def _make_index_entry(result: Dict) -> Dict:
    
    sir_hist = result.get("sir_history", [])
    final = sir_hist[-1] if sir_hist else {}
    params = result.get("params", {}) or {}
    return {
        "id": result.get("id"),
        "timestamp": result.get("timestamp", ""),
        "floor_plan_name": result.get("floor_plan_name", ""),
        "tick_count": result.get("tick_count", 0),
        "total_infections": len(result.get("transmission_events", [])),
        "final_S": final.get("S", 0),
        "final_I": final.get("I", 0),
        "final_R": final.get("R", 0),
        "num_patients": params.get("num_patients", 0),
        "num_doctors":  params.get("num_doctors",  0),
        "num_nurses":   params.get("num_nurses",   0),
    }


def load_all_runs() -> Tuple[List[Dict], Dict[str, object]]:
    
    from floorplan import FloorPlan

    entries = _read_index()
    results: List[Dict] = []
    plans: Dict[str, object] = {}

    for meta in entries:
        rid = meta.get("id")
        if not rid:
            continue
        rp = _run_path(rid)
        if not os.path.exists(rp):
            continue 
        try:
            with open(rp, "r") as f:
                results.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue

        fpp = _fp_path(rid)
        if os.path.exists(fpp):
            try:
                with open(fpp, "r") as f:
                    fp_dict = json.load(f)
                plans[rid] = FloorPlan.from_dict(fp_dict)
            except Exception:
                
                pass

    return results, plans


def delete_run(run_id: str) -> bool:
    
    removed_any = False
    for path in (_run_path(run_id), _fp_path(run_id)):
        if os.path.exists(path):
            try:
                os.remove(path)
                removed_any = True
            except OSError:
                pass
    
    entries = [e for e in _read_index() if e.get("id") != run_id]
    _write_index(entries)
    return removed_any

#CSV export

def export_result_as_csv(result: Dict) -> str:
    
    buf = io.StringIO()
    w = csv.writer(buf)

    #section 1: metadata ──
    w.writerow(["# Hospital Simulation Result"])
    w.writerow(["id", result.get("id", "")])
    w.writerow(["timestamp", result.get("timestamp", "")])
    w.writerow(["floor_plan_name", result.get("floor_plan_name", "")])
    w.writerow(["tick_count", result.get("tick_count", 0)])
    w.writerow(["total_infections", len(result.get("transmission_events", []))])
    w.writerow(["estimated_total_pop", result.get("estimated_total_pop", 0)])
    w.writerow(["total_created", result.get("total_created", 0)])

    w.writerow([])
    w.writerow(["# Parameters"])
    w.writerow(["key", "value"])
    for k, v in sorted((result.get("params") or {}).items()):
        w.writerow([k, v])

    #section 2: SIR history ──
    w.writerow([])
    w.writerow(["# SIR history"])
    w.writerow(["tick", "S", "I", "R", "current_agents", "total_agents"])
    for s in result.get("sir_history", []):
        w.writerow([
            s.get("tick", ""),
            s.get("S", ""),
            s.get("I", ""),
            s.get("R", ""),
            s.get("current_agents", ""),
            s.get("total_agents", ""),
        ])

    #section 3: transmission events ──
    w.writerow([])
    w.writerow(["# Transmission events"])
    w.writerow(["tick", "agent_id", "agent_type", "room", "dose"])
    for e in result.get("transmission_events", []):
        w.writerow([
            e.get("tick", ""),
            e.get("agent_id", ""),
            e.get("agent_type", ""),
            e.get("room", ""),
            e.get("dose", ""),
        ])

    #section 4: per-room contamination ──
    w.writerow([])
    w.writerow(["# Room cumulative contamination"])
    w.writerow(["room", "cumulative_contamination"])
    for rm, v in sorted(
        (result.get("room_contamination") or {}).items(),
        key=lambda kv: kv[1],
        reverse=True,
    ):
        w.writerow([rm, v])

    return buf.getvalue()


def export_path(run_id: str) -> str:

    _ensure_dirs()
    return os.path.join(_BASE_DIR, "exports", f"{run_id}.csv")


def write_csv_export(result: Dict) -> str:

    _ensure_dirs()
    exports_dir = os.path.join(_BASE_DIR, "exports")
    os.makedirs(exports_dir, exist_ok=True)
    run_id = result.get("id") or "latest"
    out = os.path.join(exports_dir, f"{run_id}.csv")
    with open(out, "w", newline="") as f:
        f.write(export_result_as_csv(result))
    return out
