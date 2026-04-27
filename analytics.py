import solara
import math
import uuid

from state import (
    current_page, sim_results, saved_results, model_instance,
    saved_floor_plans,
)
from ui import PALETTE, PageHeader
from persistence import save_run, write_csv_export

def _sir_svg(sir, w=380, h=220):
    if not sir:
        return (f'<svg width="{w}" height="{h}">'
                f'<rect width="{w}" height="{h}" fill="#e2eeff" rx="12"/>'
                f'<text x="{w//2}" y="{h//2}" fill="{PALETTE["text"]}" text-anchor="middle" '
                f'font-family="sans-serif" font-size="12">No data</text></svg>')

    max_tick = max(s["tick"] for s in sir) or 1
    max_count = max(max(s["S"], s["I"], s["R"]) for s in sir) or 1
    pad_l, pad_b, pad_t, pad_r = 34, 26, 30, 12
    cw = w - pad_l - pad_r
    ch = h - pad_t - pad_b

    def px(t): return pad_l + (t / max_tick) * cw
    def py(c): return pad_t + ch - (c / max_count) * ch

    step = max(1, len(sir) // 200)
    sampled = sir[::step]
    if sir[-1] not in sampled:
        sampled.append(sir[-1])

    p = [f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg" '
         f'style="background:#e2eeff;border-radius:10px;">']
    p.append(
        f'<g font-family="sans-serif" font-size="9" fill="#17048c">'
        f'<circle cx="{pad_l+10}" cy="10" r="4" fill="#22C55E"/>'
        f'<text x="{pad_l+18}" y="13">S</text>'
        f'<circle cx="{pad_l+50}" cy="10" r="4" fill="#EF4444"/>'
        f'<text x="{pad_l+58}" y="13">I</text>'
        f'<circle cx="{pad_l+90}" cy="10" r="4" fill="#9CA3AF"/>'
        f'<text x="{pad_l+98}" y="13">R</text></g>'
    )
    for frac in [0, 0.25, 0.5, 0.75, 1.0]:
        y_val = int(max_count * frac)
        y_pos = py(y_val)
        p.append(f'<text x="{pad_l-4}" y="{y_pos+3}" fill="#17048c" '
                 f'font-size="8" text-anchor="end" font-family="sans-serif">{y_val}</text>')
        if frac > 0:
            p.append(f'<line x1="{pad_l}" y1="{y_pos}" x2="{pad_l+cw}" y2="{y_pos}" '
                     f'stroke="#17048c" stroke-opacity="0.2" stroke-dasharray="3,3"/>')
    for frac in [0.25, 0.5, 0.75, 1.0]:
        x_val = int(max_tick * frac)
        x_pos = px(x_val)
        p.append(f'<text x="{x_pos}" y="{pad_t+ch+14}" fill="#17048c" '
                 f'font-size="8" text-anchor="middle" font-family="sans-serif">{x_val}</text>')
    p.append(f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t+ch}" stroke="#17048c"/>')
    p.append(f'<line x1="{pad_l}" y1="{pad_t+ch}" x2="{pad_l+cw}" y2="{pad_t+ch}" stroke="#17048c"/>')
    for key, col in [("S", "#22C55E"), ("I", "#EF4444"), ("R", "#9CA3AF")]:
        pts = " ".join(f"{px(s['tick'])},{py(s[key])}" for s in sampled)
        p.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2"/>')
    p.append('</svg>')
    return "\n".join(p)


def _cumulative_infections_svg(new_inf, w=380, h=220):
    if not new_inf or sum(new_inf) == 0:
        return (f'<svg width="{w}" height="{h}">'
                f'<rect width="{w}" height="{h}" fill="#e2eeff" rx="10"/>'
                f'<text x="{w//2}" y="{h//2}" fill="{PALETTE["text"]}" text-anchor="middle" '
                f'font-family="sans-serif" font-size="12">No infections</text></svg>')

    cum = []
    running = 0
    for v in new_inf:
        running += v
        cum.append(running)

    max_count = cum[-1] or 1
    max_tick = len(cum) or 1
    pad_l, pad_b, pad_t, pad_r = 34, 26, 30, 12
    cw = w - pad_l - pad_r
    ch = h - pad_t - pad_b

    def px(t): return pad_l + (t / max_tick) * cw
    def py(c): return pad_t + ch - (c / max_count) * ch

    step = max(1, len(cum) // 200)
    sampled = list(enumerate(cum))[::step]
    if (len(cum) - 1, cum[-1]) not in sampled:
        sampled.append((len(cum) - 1, cum[-1]))

    p = [f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg" '
         f'style="background:#e2eeff;border-radius:10px;">']
    avg_rate = cum[-1] / len(cum)
    p.append(
        f'<g font-family="sans-serif" font-size="9" fill="#17048c">'
        f'<line x1="{pad_l+6}" y1="10" x2="{pad_l+22}" y2="10" '
        f'stroke="#EF4444" stroke-width="2"/>'
        f'<text x="{pad_l+26}" y="13">Cumulative</text>'
        f'<text x="{pad_l+100}" y="13" opacity="0.7">(avg {avg_rate:.3f}/tick)</text>'
        f'</g>'
    )
    for frac in [0, 0.25, 0.5, 0.75, 1.0]:
        y_val = int(max_count * frac)
        y_pos = py(y_val)
        p.append(f'<text x="{pad_l-4}" y="{y_pos+3}" fill="#17048c" '
                 f'font-size="8" text-anchor="end" font-family="sans-serif">{y_val}</text>')
        if frac > 0:
            p.append(f'<line x1="{pad_l}" y1="{y_pos}" x2="{pad_l+cw}" y2="{y_pos}" '
                     f'stroke="#17048c" stroke-opacity="0.2" stroke-dasharray="3,3"/>')
    for frac in [0.25, 0.5, 0.75, 1.0]:
        x_val = int(max_tick * frac)
        x_pos = px(x_val)
        p.append(f'<text x="{x_pos}" y="{pad_t+ch+14}" fill="#17048c" '
                 f'font-size="8" text-anchor="middle" font-family="sans-serif">{x_val}</text>')
    p.append(f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t+ch}" stroke="#17048c"/>')
    p.append(f'<line x1="{pad_l}" y1="{pad_t+ch}" x2="{pad_l+cw}" y2="{pad_t+ch}" stroke="#17048c"/>')
    area_pts = " ".join(f"{px(i)},{py(v)}" for i, v in sampled)
    area_poly = (f"{pad_l},{pad_t+ch} " + area_pts + f" {px(sampled[-1][0])},{pad_t+ch}")
    p.append(f'<polygon points="{area_poly}" fill="#EF4444" fill-opacity="0.15"/>')
    pts = " ".join(f"{px(i)},{py(v)}" for i, v in sampled)
    p.append(f'<polyline points="{pts}" fill="none" stroke="#EF4444" stroke-width="2.2"/>')
    p.append('</svg>')
    return "\n".join(p)


def _pie_svg(data, w=260, h=260):
    data = [(lbl, v, col) for (lbl, v, col) in data if v > 0]
    total = sum(v for _, v, _ in data)
    if total == 0:
        return (f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg" '
                f'style="background:#e2eeff;border-radius:10px;">'
                f'<text x="{w//2}" y="{h//2}" fill="{PALETTE["text"]}" text-anchor="middle" '
                f'font-family="sans-serif" font-size="12">No infections</text></svg>')

    pie_size = min(w - 20, 180)
    cx = w // 2
    cy = 10 + pie_size // 2
    r = pie_size // 2 - 4
    legend_top = cy + pie_size // 2 + 14
    row_h = 14
    needed_h = legend_top + row_h * len(data) + 8
    svg_h = max(h, needed_h)

    p = [f'<svg width="{w}" height="{svg_h}" xmlns="http://www.w3.org/2000/svg" '
         f'style="background:#e2eeff;border-radius:10px;">']
    angle = 0.0
    for label, val, col in data:
        frac = val / total
        sweep = frac * 360
        a1 = math.radians(angle - 90)
        a2 = math.radians(angle + sweep - 90)
        x1 = cx + r * math.cos(a1)
        y1 = cy + r * math.sin(a1)
        x2 = cx + r * math.cos(a2)
        y2 = cy + r * math.sin(a2)
        large = 1 if sweep > 180 else 0
        p.append(
            f'<path d="M{cx},{cy} L{x1},{y1} A{r},{r} 0 {large} 1 {x2},{y2} Z" '
            f'fill="{col}" stroke="#17048c" stroke-width="1"/>'
        )
        if frac >= 0.08:
            mid = math.radians(angle + sweep / 2 - 90)
            tx = cx + (r * 0.62) * math.cos(mid)
            ty = cy + (r * 0.62) * math.sin(mid)
            p.append(
                f'<text x="{tx}" y="{ty+4}" fill="#ffffff" font-size="11" '
                f'text-anchor="middle" font-weight="bold" '
                f'font-family="sans-serif">{frac:.0%}</text>'
            )
        angle += sweep

    ly = legend_top
    for label, val, col in data:
        display_label = label if len(label) <= 16 else label[:15] + "…"
        pct = (val / total) * 100
        p.append(
            f'<rect x="10" y="{ly-8}" width="10" height="10" '
            f'fill="{col}" stroke="#17048c" stroke-width="0.5" rx="2"/>'
        )
        p.append(
            f'<text x="24" y="{ly}" fill="#17048c" font-size="10" '
            f'font-family="sans-serif">'
            f'{display_label} ({val}·{pct:.0f}%)</text>'
        )
        ly += row_h
    p.append('</svg>')
    return "\n".join(p)


def _heatmap_floor_plan_svg(floor_plan, room_contam, w=700, h=480):
    if floor_plan is None:
        return (f'<svg width="{w}" height="{h}">'
                f'<rect width="{w}" height="{h}" fill="#17048c" rx="12"/>'
                f'<text x="{w//2}" y="{h//2}" fill="#ffffff" text-anchor="middle" '
                f'font-family="sans-serif" font-size="12">No floor plan</text></svg>')

    max_c = max(room_contam.values(), default=0.0) if room_contam else 0.0
    if max_c <= 0:
        max_c = 1e-9

    fp = floor_plan
    sx = w / fp.width
    sy = h / fp.height
    scale = min(sx, sy) * 0.9
    ox = (w - fp.width * scale) / 2
    oy = (h - fp.height * scale) / 2 + 8

    def tx(x): return ox + x * scale
    def ty(y): return oy + y * scale
    def ts(v): return v * scale

    def heat_colour(val):
        t = min(1.0, val / max_c) if max_c > 0 else 0.0
        if t < 0.5:
            u = t / 0.5
            r = int(0x22 + (0xEA - 0x22) * u)
            g = int(0xC5 + (0xB3 - 0xC5) * u)
            b = int(0x5E + (0x08 - 0x5E) * u)
        else:
            u = (t - 0.5) / 0.5
            r = int(0xEA + (0xEF - 0xEA) * u)
            g = int(0xB3 + (0x44 - 0xB3) * u)
            b = int(0x08 + (0x44 - 0x08) * u)
        return f"#{r:02x}{g:02x}{b:02x}"

    parts = [f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg" '
             f'style="background:#17048c;border-radius:12px;">']

    _ABBR = [("Pa","patient"),("Dr","doctor"),("Nu","nurse"),
             ("Vi","visitor"),("Cl","cleaner"),("Vo","volunteer")]

    for r in fp.rooms:
        val = room_contam.get(r.name, 0.0) if room_contam else 0.0
        fill = heat_colour(val)
        pts = " ".join(f"{tx(p[0])},{ty(p[1])}" for p in r.polygon)
        parts.append(
            f'<polygon points="{pts}" fill="{fill}" stroke="#17048c" '
            f'stroke-width="1" opacity="0.95"/>'
        )
        cx = sum(p[0] for p in r.polygon) / len(r.polygon)
        cy = sum(p[1] for p in r.polygon) / len(r.polygon)
        text_col = "#17048c" if (val / max_c) < 0.7 else "#ffffff"
        no_access = " ".join(a for a, t in _ABBR if t not in r.access)
        parts.append(
            f'<text x="{tx(cx)}" y="{ty(cy)-9}" fill="{text_col}" font-size="9" '
            f'text-anchor="middle" font-family="monospace" font-weight="bold">{r.name}</text>'
        )
        parts.append(
            f'<text x="{tx(cx)}" y="{ty(cy)+1}" fill="{text_col}" font-size="7" '
            f'text-anchor="middle" font-family="monospace" opacity="0.75">'
            f'{r.ventilation_ach:.0f} ACH · {r.volume_m3:.0f}m³</text>'
        )
        if no_access:
            parts.append(
                f'<text x="{tx(cx)}" y="{ty(cy)+11}" fill="#EF4444" font-size="7" '
                f'text-anchor="middle" font-family="monospace" font-weight="bold">'
                f'✗ {no_access}</text>'
            )

    for ws, we in fp.walls:
        parts.append(
            f'<line x1="{tx(ws[0])}" y1="{ty(ws[1])}" '
            f'x2="{tx(we[0])}" y2="{ty(we[1])}" stroke="#0F172A" stroke-width="2"/>'
        )
    for d in fp.doors:
        parts.append(
            f'<circle cx="{tx(d.position[0])}" cy="{ty(d.position[1])}" '
            f'r="{ts(3)}" fill="#cb6ce6" opacity="0.95"/>'
        )
    for e in fp.entrances:
        parts.append(
            f'<circle cx="{tx(e.position[0])}" cy="{ty(e.position[1])}" '
            f'r="{ts(8)}" fill="#22C55E" opacity="0.3" stroke="#22C55E" stroke-width="2"/>'
        )
        parts.append(
            f'<text x="{tx(e.position[0])}" y="{ty(e.position[1])-ts(10)}" '
            f'fill="#22C55E" font-size="8" text-anchor="middle" font-weight="bold" '
            f'font-family="monospace">ENTRY</text>'
        )

    bar_y = h - 18
    bar_w = w - 80
    stops = 40
    step = bar_w / stops
    for i in range(stops):
        frac = i / (stops - 1)
        parts.append(
            f'<rect x="{40 + i*step}" y="{bar_y}" width="{step+0.5}" '
            f'height="8" fill="{heat_colour(frac * max_c)}"/>'
        )
    parts.append(f'<text x="40" y="{bar_y-2}" fill="#ffffff" font-size="9" font-family="sans-serif">low</text>')
    parts.append(f'<text x="{40+bar_w/2}" y="{bar_y-2}" fill="#ffffff" font-size="9" text-anchor="middle" font-family="sans-serif">medium</text>')
    parts.append(f'<text x="{40+bar_w}" y="{bar_y-2}" fill="#ffffff" font-size="9" text-anchor="end" font-family="sans-serif">high</text>')
    parts.append('</svg>')
    return "\n".join(parts)


def _infection_log_html(events, max_rows=None):
    if not events:
        return (
            f'<div style="background:#e2eeff;border-radius:8px;padding:12px;width:100%;max-width:250px;margin:0 auto;'
            f'color:{PALETTE["text"]};opacity:0.6;font-size:10px;'
            f'font-style:italic;text-align:center;">No infections occurred</div>'
        )
    shown = list(reversed(events))
    if max_rows is not None:
        shown = shown[:max_rows]
    rows = []
    for e in shown:
        at = e.get("agent_type", "?").title()
        rm = e.get("room", "?")
        aid = e.get("agent_id", "?")
        tk = e.get("tick", 0)
        rows.append(
            f'<div style="font-size:9px;color:{PALETTE["text"]};padding:4px 6px;width:350px;'
            f'margin:2px 0;background:#cc6ce65f;border-left:3px solid #cb6ce6;'
            f'border-radius:4px;">'
            f'<b>t={tk}</b> — {at} #{aid}<br/>'
            f'<span style="opacity:0.75;font-weight:500;">in {rm}</span>'
            f'</div>'
        )
    header = (
        f'<div style="font-size:10px;color:{PALETTE["text"]};opacity:0.7;'
        f'padding:4px 6px;font-weight:600;">'
        f'{len(events)} infection{"s" if len(events) != 1 else ""} total</div>'
    )
    return (
        f'<div style="max-height:340px;overflow-y:auto;background:#e2eeff;'
        f'border-radius:8px;padding:4px;width:100%;box-sizing:border-box;">'
        + header + "".join(rows) + '</div>'
    )


def _settings_panel_html(params, floor_plan_name, fp_height=None):
    fp_rows = [("Layout", floor_plan_name)]
    if fp_height is not None:
        fp_rows.append(("Height", f"{fp_height} units"))
    groups = [
        ("Floor Plan", fp_rows),
        ("Population", [
            ("Patients", params.get("num_patients")),
            ("Doctors", params.get("num_doctors")),
            ("Nurses", params.get("num_nurses")),
            ("Cleaners", params.get("num_cleaners")),
            ("Volunteers", params.get("num_volunteers")),
            ("Initially infected", params.get("num_initially_infected")),
        ]),
        ("Arrivals", [
            ("Patient interval", f"{params.get('patient_arrival_interval')} ticks"),
            ("Infected on arrival", f"{params.get('infected_arrival_fraction', 0):.0%}"),
            ("Visitor interval", f"{params.get('visitor_arrival_interval')} ticks"),
            ("Visiting hours",
             f"{params.get('visiting_hours_start')}–{params.get('visiting_hours_end')}"),
        ]),
        ("Pathogen", [
            ("Quanta rate", f"{params.get('quanta_rate')} q/h"),
            ("Near-field radius", f"{params.get('near_field_radius')} m"),
            ("Air speed", f"{params.get('random_air_speed')} m/min"),
            ("Recovery rate", f"{params.get('recovery_rate')} /tick"),
        ]),
        ("Interventions", [
            ("Mask efficiency", f"{params.get('mask_efficiency', 0):.0%}"),
            ("HEPA CADR", f"{params.get('hepa_cadr')} m³/h"),
        ]),
        ("Control", [
            ("Timestep", f"{params.get('delta_t')} h"),
            ("Speed", f"{params.get('sim_speed')} t/s"),
            ("Max steps", params.get('max_steps')),
            ("Seed", params.get('random_seed')),
        ]),
    ]
    blocks = []
    for title, rows in groups:
        body = "".join(
            f'<div style="display:flex;justify-content:space-between;'
            f'font-size:10px;color:#17048c;padding:2px 0;">'
            f'<span style="opacity:0.7;">{k}</span>'
            f'<b>{v}</b></div>'
            for k, v in rows
        )
        blocks.append(
            f'<div style="background:#e2eeff;border-radius:8px;padding:8px;'
            f'margin-bottom:6px;">'
            f'<div style="font-weight:700;color:#17048c;font-size:11px;'
            f'margin-bottom:4px;">{title}</div>{body}</div>'
        )
    return "".join(blocks)


@solara.component
def AnalyticsPage():
    res = sim_results.value
    csv_export_path, set_csv_export_path = solara.use_state("")

    if res is None:
        with solara.Column(
            style={"min-height": "100vh", "background": PALETTE["bg"], "padding": "40px"}
        ):
            PageHeader(subtitle="Results & Analysis", back_page="home", back_label="← Home")
            solara.HTML(
                tag="div",
                unsafe_innerHTML=(
                    f'<div style="text-align:center;color:{PALETTE["text"]};'
                    f'padding:40px;opacity:0.7;">No results yet.</div>'
                ),
            )
        return

    sir = res.get("sir_history", [])
    new_inf = res.get("new_infections_per_tick", [])
    events = res.get("transmission_events", [])
    room_contam = res.get("room_contamination", {})
    params = res.get("params", {})

    floor_plan = None
    rid = res.get("id")
    if rid and rid in saved_floor_plans.value:
        floor_plan = saved_floor_plans.value[rid]
    elif model_instance.value is not None:
        floor_plan = model_instance.value.floor_plan

    CARD = {
        "background": PALETTE["card"],
        "border-radius": "16px",
        "padding": "16px",
        "gap": "10px",
    }

    def card_title(txt):
        return (
            f'<div style="color:{PALETTE["text"]};font-weight:700;font-size:13px;'
            f'margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid #e2eeff;">'
            f'{txt}</div>'
        )

  
    room_infection_counts = {}
    for e in events:
        rm = e.get("room", "?") or "(unknown)"
        room_infection_counts[rm] = room_infection_counts.get(rm, 0) + 1
    sorted_rooms = sorted(room_infection_counts.items(), key=lambda kv: kv[1], reverse=True)
    PIE_PALETTE = [
        "#EF4444", "#F97316", "#EAB308", "#22C55E", "#14B8A6",
        "#3B82F6", "#8B5CF6", "#EC4899", "#F59E0B", "#10B981", "#06B6D4", "#A855F7",
    ]
    pie_data = [
        (name, cnt, PIE_PALETTE[i % len(PIE_PALETTE)])
        for i, (name, cnt) in enumerate(sorted_rooms)
    ]

    already_saved = res is not None and res.get("id") in {
        r.get("id") for r in saved_results.value if r.get("id")
    }

    def save_result():
        current_res = sim_results.value
        if current_res is None:
            return
        if "id" not in current_res:
            current_res = dict(current_res)
            current_res["id"] = str(uuid.uuid4())
            sim_results.set(current_res)
        run_id = current_res["id"]
        existing_ids = {r.get("id") for r in saved_results.value}
        if run_id not in existing_ids:
            new_list = saved_results.value.copy()
            new_list.append(current_res)
            saved_results.set(new_list)
        fp_for_run = None
        if model_instance.value is not None:
            fp_for_run = model_instance.value.floor_plan
        elif run_id in saved_floor_plans.value:
            fp_for_run = saved_floor_plans.value[run_id]
        if fp_for_run is not None:
            fps = saved_floor_plans.value.copy()
            fps[run_id] = fp_for_run
            saved_floor_plans.set(fps)
        try:
            save_run(current_res, floor_plan=fp_for_run)
        except Exception as exc:
            print(f"[save_run] failed: {exc}")

    def export_csv():
        current_res = sim_results.value
        if current_res is None:
            return
        if "id" not in current_res:
            current_res = dict(current_res)
            current_res["id"] = str(uuid.uuid4())
            sim_results.set(current_res)
        try:
            out = write_csv_export(current_res)
            set_csv_export_path(out)
        except Exception as exc:
            set_csv_export_path(f"Error: {exc}")

    with solara.Column(
        style={"min-height": "100vh", "background": PALETTE["bg"],
               "padding": "20px", "gap": "14px"}
    ):
        PageHeader(
            subtitle="Results & Analysis",
            back_page="simulation",
            back_label="← Simulation",
        )

        with solara.Row(
            style={"gap": "16px", "background": "transparent",
                   "align-items": "flex-start"}
        ):

            with solara.Column(
                style={
                    "width": "240px",
                    "min-width": "240px",
                    "background": PALETTE["card"],
                    "border-radius": "18px",
                    "padding": "14px",
                    "gap": "8px",
                }
            ):
                solara.HTML(
                    tag="div",
                    unsafe_innerHTML=(
                        f'<div style="color:{PALETTE["text"]};font-weight:700;'
                        f'font-size:14px;text-align:center;margin-bottom:4px;'
                        f'padding-bottom:8px;border-bottom:2px solid #e2eeff;">'
                        f'Simulation Settings</div>'
                    ),
                )
                fp_name = res.get("floor_plan_name", "")
                fp_h = floor_plan.height if floor_plan else None
                solara.HTML(
                    tag="div",
                    unsafe_innerHTML=_settings_panel_html(params, fp_name, fp_height=fp_h),
                )


            with solara.Column(
                style={"flex": "1", "gap": "14px", "background": "transparent",
                       "min-width": "0"}
            ):

                with solara.Row(
                    style={"gap": "14px", "flex-wrap": "wrap",
                           "background": "transparent"}
                ):
                    with solara.Column(
                        style={**CARD, "flex": "1 1 340px", "min-width": "300px",
                               "align-items": "center"}
                    ):
                        solara.HTML(tag="div", unsafe_innerHTML=card_title("SIR Infection Graph"))
                        solara.HTML(tag="div", unsafe_innerHTML=_sir_svg(sir, 360, 220))

                    with solara.Column(
                        style={**CARD, "flex": "1 1 340px", "min-width": "300px",
                               "align-items": "center"}
                    ):
                        solara.HTML(tag="div", unsafe_innerHTML=card_title("Cumulative Infections"))
                        solara.HTML(
                            tag="div",
                            unsafe_innerHTML=_cumulative_infections_svg(new_inf, 360, 220),
                        )

                    with solara.Column(
                        style={**CARD, "flex": "1 1 340px", "min-width": "300px",
                               "align-items": "center"}
                    ):
                        solara.HTML(tag="div", unsafe_innerHTML=card_title("Infection Log"))
                        solara.HTML(tag="div", unsafe_innerHTML=_infection_log_html(events))

                    with solara.Column(
                        style={**CARD, "flex": "1 1 340px", "min-width": "300px",
                               "align-items": "center"}
                    ):
                        solara.HTML(tag="div", unsafe_innerHTML=card_title("Infections per Room"))
                        solara.HTML(tag="div", unsafe_innerHTML=_pie_svg(pie_data, 260, 280))

                with solara.Column(style={**CARD, "align-items": "center"}):
                    solara.HTML(tag="div", unsafe_innerHTML=card_title("Infection Heatmap"))
                    solara.HTML(
                        tag="div",
                        unsafe_innerHTML=(
                            f'<div style="overflow-x:auto;">'
                            f'{_heatmap_floor_plan_svg(floor_plan, room_contam, 700, 460)}'
                            f'</div>'
                        ),
                    )

                with solara.Row(
                    style={"gap": "10px", "background": "transparent",
                           "flex-wrap": "wrap", "align-items": "center",
                           "justify-content": "space-between"}
                ):

                    with solara.Row(style={"gap": "10px", "background": "transparent",
                                          "align-items": "center", "flex-wrap": "wrap"}):
                        solara.Button(
                            label="Saved" if already_saved else "Save",
                            on_click=save_result,
                            style={
                                "text-transform": "none",
                                "background": PALETTE["accent"] if already_saved else PALETTE["primary"],
                                "color": PALETTE["text"] if already_saved else "#ffffff",
                                "border-radius": "20px",
                                "padding": "10px 28px",
                                "font-weight": "700",
                            },
                        )
                        solara.Button(
                            label="Export CSV",
                            on_click=export_csv,
                            style={
                                "text-transform": "none",
                                "background": PALETTE["pink"],
                                "color": "#ffffff",
                                "border-radius": "20px",
                                "padding": "10px 28px",
                                "font-weight": "700",
                            },
                        )
                        if csv_export_path:
                            solara.HTML(
                                tag="div",
                                unsafe_innerHTML=(
                                    f'<div style="font-size:10px;color:{PALETTE["text"]};'
                                    f'background:{PALETTE["card"]};border-radius:8px;'
                                    f'padding:8px;word-break:break-all;">'
                                    f'<b>CSV:</b> {csv_export_path}</div>'
                                ),
                            )

                    solara.Button(
                        label="Home  →",
                        on_click=lambda: current_page.set("home"),
                        style={
                            "text-transform": "none",
                            "background": PALETTE["primary"],
                            "color": "#ffffff",
                            "border-radius": "20px",
                            "padding": "10px 28px",
                            "font-weight": "700",
                        },
                    )
