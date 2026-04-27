import solara
import math
import time
import threading

from state import (
    current_page, sim_params, model_instance,
    sim_running, sim_paused, sim_tick, sim_results, saved_results,
    saved_floor_plans,
)
from agents import (
    HospitalAgent, PatientAgent, DoctorAgent, NurseAgent, CleanerAgent,
    AGENT_SHAPES, STATUS_COLOURS, Status,
)
from ui import PALETTE, PageHeader


#svg

def _shape(sh, cx, cy, r, fill):
    
    stroke = 'stroke="#0F172A" stroke-width="0.8"'
    if sh == "circle":
        return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" {stroke}/>'
    if sh == "diamond":
        return (f'<polygon points="{cx},{cy-r} {cx+r},{cy} {cx},{cy+r} '
                f'{cx-r},{cy}" fill="{fill}" {stroke}/>')
    if sh == "square":
        return (f'<rect x="{cx-r}" y="{cy-r}" width="{r*2}" height="{r*2}" '
                f'fill="{fill}" {stroke} rx="1"/>')
    if sh == "triangle_up":
        return (f'<polygon points="{cx},{cy-r} {cx+r},{cy+r*.7} {cx-r},{cy+r*.7}" '
                f'fill="{fill}" {stroke}/>')
    if sh == "triangle_down":
        return (f'<polygon points="{cx-r},{cy-r*.7} {cx+r},{cy-r*.7} {cx},{cy+r}" '
                f'fill="{fill}" {stroke}/>')
    if sh == "hexagon":
        pts = " ".join(
            f"{cx+r*math.cos(math.radians(60*i-30))},{cy+r*math.sin(math.radians(60*i-30))}"
            for i in range(6)
        )
        return f'<polygon points="{pts}" fill="{fill}" {stroke}/>'
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}"/>'


def _conc_col(c, mx=0.05):
    
    if mx <= 0:
        mx = 0.05
    t = min(1.0, c / mx)
    if t < 0.5:
        # green -> yellow
        u = t / 0.5
        r = int(0x22 + (0xEA - 0x22) * u)
        g = int(0xC5 + (0xC4 - 0xC5) * u)
        b = int(0x5E + (0x0B - 0x5E) * u)
    else:
        # yellow -> red
        u = (t - 0.5) / 0.5
        r = int(0xEA + (0xEF - 0xEA) * u)
        g = int(0xC4 + (0x44 - 0xC4) * u)
        b = int(0x0B + (0x44 - 0x0B) * u)
    return f"#{r:02x}{g:02x}{b:02x}"


def _render_fp(model, w=780, h=520):

    if model is None:
        return (f'<svg width="{w}" height="{h}">'
                f'<text x="{w//2}" y="{h//2}" fill="#94A3B8" '
                f'text-anchor="middle">No simulation</text></svg>')

    fp = model.floor_plan
    sx = w / fp.width
    sy = h / fp.height
    sc = min(sx, sy) * 0.92
    ox = (w - fp.width * sc) / 2
    oy = (h - fp.height * sc) / 2

    def tx(x): return ox + x * sc
    def ty(y): return oy + y * sc
    def ts(v): return v * sc

    mx = max((r.C_FF for r in fp.rooms), default=0.01) or 0.01

    p = [f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg" '
         f'style="background:#0F172A;border-radius:12px;">']
    p.append(f'<rect x="{tx(0)}" y="{ty(0)}" width="{fp.width*sc}" '
             f'height="{fp.height*sc}" fill="#1a2332" rx="4"/>')

    _ABBR = [("Pa","patient"),("Dr","doctor"),("Nu","nurse"),
             ("Vi","visitor"),("Cl","cleaner"),("Vo","volunteer")]

    for r in fp.rooms:
        pts = " ".join(f"{tx(pt[0])},{ty(pt[1])}" for pt in r.polygon)
        p.append(f'<polygon points="{pts}" fill="{_conc_col(r.C_FF, mx)}" '
                 f'stroke="#334155" stroke-width="1.5" opacity="0.65"/>')
        cx = sum(pt[0] for pt in r.polygon) / len(r.polygon)
        cy = sum(pt[1] for pt in r.polygon) / len(r.polygon)
        no_access = " ".join(a for a, t in _ABBR if t not in r.access)
        p.append(f'<text x="{tx(cx)}" y="{ty(cy)-9}" fill="#0F172A" font-size="8" '
                 f'text-anchor="middle" font-family="monospace" font-weight="bold">{r.name}</text>')
        p.append(f'<text x="{tx(cx)}" y="{ty(cy)+1}" fill="#0F172A" font-size="6" '
                 f'text-anchor="middle" font-family="monospace" opacity="0.7">'
                 f'{r.ventilation_ach:.0f} ACH · {r.volume_m3:.0f}m³</text>')
        if no_access:
            p.append(f'<text x="{tx(cx)}" y="{ty(cy)+11}" fill="#EF4444" font-size="6.5" '
                     f'text-anchor="middle" font-family="monospace" font-weight="bold">'
                     f'✗ {no_access}</text>')

    for ws, we in fp.walls:
        p.append(f'<line x1="{tx(ws[0])}" y1="{ty(ws[1])}" '
                 f'x2="{tx(we[0])}" y2="{ty(we[1])}" stroke="#475569" stroke-width="2"/>')

    for d in fp.doors:
        p.append(f'<circle cx="{tx(d.position[0])}" cy="{ty(d.position[1])}" '
                 f'r="{ts(3)}" fill="#F97316" opacity="0.6"/>')

    for b in fp.beds:
        bx, by = b.position
        p.append(f'<rect x="{tx(bx)-ts(5)}" y="{ty(by)-ts(3)}" '
                 f'width="{ts(10)}" height="{ts(6)}" fill="#3B82F6" rx="1.5" opacity="0.7"/>')

    for e in fp.entrances:
        p.append(f'<circle cx="{tx(e.position[0])}" cy="{ty(e.position[1])}" '
                 f'r="{ts(8)}" fill="#22C55E" opacity="0.3" stroke="#22C55E" stroke-width="1.5"/>')
        p.append(f'<text x="{tx(e.position[0])}" y="{ty(e.position[1])-ts(10)}" '
                 f'fill="#22C55E" font-size="9" text-anchor="middle" font-weight="bold" '
                 f'font-family="monospace">ENTRY</text>')

    for a in model._living_agents():
        if a.pos is None:
            continue
        fill = STATUS_COLOURS.get(a.status, "#888")
        sh = AGENT_SHAPES.get(a.agent_type, "circle")
        p.append(_shape(sh, tx(a.pos[0]), ty(a.pos[1]), ts(4), fill))

    p.append('</svg>')
    return "\n".join(p)


def _sir_chart_html(sir, w=290, h=150):

    if not sir:
        return (f'<svg width="{w}" height="{h}">'
                f'<rect width="{w}" height="{h}" fill="#e2eeff" rx="8"/>'
                f'<text x="{w//2}" y="{h//2}" fill="#17048c" text-anchor="middle" '
                f'font-size="10">Waiting…</text></svg>')
    mt = max(s["tick"] for s in sir) or 1
    mc = max(max(s["S"], s["I"], s["R"]) for s in sir) or 1
    pad = 28
    cw = w - pad - 8
    ch = h - pad - 12

    def px(t): return pad + (t / mt) * cw
    def py(c): return 10 + ch - (c / mc) * ch

    step = max(1, len(sir) // 200)
    sampled = sir[::step]
    if sir[-1] not in sampled:
        sampled.append(sir[-1])

    p = [f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg">'
         f'<rect width="{w}" height="{h}" fill="#e2eeff" rx="8"/>']
    p.append(f'<line x1="{pad}" y1="10" x2="{pad}" y2="{10+ch}" stroke="#17048c" stroke-opacity="0.4"/>')
    p.append(f'<line x1="{pad}" y1="{10+ch}" x2="{pad+cw}" y2="{10+ch}" stroke="#17048c" stroke-opacity="0.4"/>')
    p.append(f'<text x="{pad-3}" y="14" fill="#17048c" font-size="8" text-anchor="end">{mc}</text>')
    p.append(f'<text x="{pad+cw}" y="{10+ch+10}" fill="#17048c" font-size="8" text-anchor="end">{mt}</text>')

    for key, col in [("S", "#22C55E"), ("I", "#EF4444"), ("R", "#9CA3AF")]:
        pts = " ".join(f"{px(s['tick'])},{py(s[key])}" for s in sampled)
        p.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="1.6"/>')

    #legend
    lx = pad + 4
    p.append(f'<circle cx="{lx}" cy="{h-5}" r="3" fill="#22C55E"/><text x="{lx+6}" y="{h-2}" fill="#17048c" font-size="8">S</text>')
    p.append(f'<circle cx="{lx+22}" cy="{h-5}" r="3" fill="#EF4444"/><text x="{lx+28}" y="{h-2}" fill="#17048c" font-size="8">I</text>')
    p.append(f'<circle cx="{lx+44}" cy="{h-5}" r="3" fill="#9CA3AF"/><text x="{lx+50}" y="{h-2}" fill="#17048c" font-size="8">R</text>')
    p.append('</svg>')
    return "\n".join(p)




def _legend_html():
    
    def tile(svg, label):
        return (
            f'<div style="display:flex;align-items:center;gap:8px;padding:4px 6px;">'
            f'<svg width="18" height="18" viewBox="0 0 18 18">{svg}</svg>'
            f'<span style="color:#17048c;font-size:11px;">{label}</span></div>'
        )
    fill = '#17048c'
    glyphs = {
        "circle":        f'<circle cx="9" cy="9" r="6" fill="{fill}"/>',
        "diamond":       f'<polygon points="9,2 16,9 9,16 2,9" fill="{fill}"/>',
        "square":        f'<rect x="3" y="3" width="12" height="12" fill="{fill}" rx="1"/>',
        "triangle_up":   f'<polygon points="9,2 16,15 2,15" fill="{fill}"/>',
        "triangle_down": f'<polygon points="2,3 16,3 9,16" fill="{fill}"/>',
        "hexagon":       ('<polygon points="9,2 15.5,5.5 15.5,12.5 9,16 2.5,12.5 2.5,5.5" '
                          f'fill="{fill}"/>'),
    }
    rows = [
        tile(glyphs["circle"],        "Patient"),
        tile(glyphs["diamond"],       "Doctor"),
        tile(glyphs["square"],        "Nurse"),
        tile(glyphs["triangle_up"],   "Visitor"),
        tile(glyphs["triangle_down"], "Cleaner"),
        tile(glyphs["hexagon"],       "Volunteer"),
    ]
    agents_block = (
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:2px;'
        'background:#e2eeff;border-radius:8px;padding:4px;">'
        + "".join(rows) + '</div>'
    )

    def dot(col, label):
        return (
            f'<div style="display:flex;align-items:center;gap:6px;">'
            f'<span style="width:12px;height:12px;border-radius:50%;'
            f'background:{col};display:inline-block;"></span>'
            f'<span style="color:#17048c;font-size:11px;">{label}</span></div>'
        )
    status_block = (
        '<div style="display:flex;gap:10px;justify-content:space-around;'
        'background:#e2eeff;border-radius:8px;padding:6px;margin-top:4px;">'
        + dot("#22C55E", "S") + dot("#EF4444", "I") + dot("#9CA3AF", "R") + '</div>'
    )
    return (
        '<div style="font-weight:700;color:#17048c;font-size:12px;margin-bottom:4px;">'
        'Agents &amp; Status</div>' + agents_block + status_block
    )


def _room_contam_bars_html(model, max_rows=10):
    if model is None:
        return ''
    rooms = sorted(model.floor_plan.rooms, key=lambda r: r.C_FF, reverse=True)[:max_rows]
    mx = max((r.C_FF for r in rooms), default=0.01) or 0.01
    rows = []
    for rm in rooms:
        pct = min(100, (rm.C_FF / mx) * 100)
        intensity = min(1.0, rm.C_FF / mx)
        if intensity < 0.5:
            col = "#d3e65c"
        elif intensity < 0.8:
            col = "#F97316"
        else:
            col = "#EF4444"
        rows.append(
            f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0;">'
            f'<div style="width:70px;font-size:9px;color:#17048c;'
            f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{rm.name}</div>'
            f'<div style="flex:1;height:8px;background:#ffffff;border-radius:4px;overflow:hidden;">'
            f'<div style="width:{pct}%;height:100%;background:{col};"></div></div>'
            f'<div style="font-size:8px;color:#17048c;width:42px;text-align:right;">'
            f'{rm.C_FF:.4f}</div></div>'
        )
    return (
        '<div style="font-weight:700;color:#17048c;font-size:12px;margin-bottom:4px;">'
        'Room Contamination Probability</div>'
        '<div style="background:#e2eeff;border-radius:8px;padding:8px;">'
        + "".join(rows) + '</div>'
    )


def _agent_counts_html(model):

    if model is None:
        return ''
    status_counts = {t: [0, 0, 0] for t in ("patient", "doctor", "nurse",
                                              "visitor", "cleaner", "volunteer")}
    for a in model._living_agents():
        if a.agent_type in status_counts:
            idx = {"S": 0, "I": 1, "R": 2}.get(a.status, 0)
            status_counts[a.agent_type][idx] += 1
    rows = []
    for t in ["patient", "doctor", "nurse", "visitor", "cleaner", "volunteer"]:
        s, i, r = status_counts[t]
        total = s + i + r
        rows.append(
            f'<div style="display:grid;grid-template-columns:70px 30px 1fr;gap:4px;'
            f'align-items:center;padding:2px 4px;">'
            f'<div style="font-size:10px;color:#17048c;text-transform:capitalize;">{t}</div>'
            f'<div style="font-size:13px;color:#17048c;font-weight:700;text-align:right;">{total}</div>'
            f'<div style="font-size:9px;color:#17048c;text-align:right;opacity:0.85;">'
            f'<span style="color:#22C55E;">S:{s}</span> '
            f'<span style="color:#EF4444;">I:{i}</span> '
            f'<span style="color:#9CA3AF;">R:{r}</span></div></div>'
        )
    return (
        '<div style="font-weight:700;color:#17048c;font-size:12px;margin-bottom:4px;">'
        'Agents in Simulation</div>'
        '<div style="background:#e2eeff;border-radius:8px;padding:4px;">'
        + "".join(rows) + '</div>'
    )


def _infection_log_html(model, max_rows=20):

    if model is None or not model.transmission_events:
        return (
            '<div style="font-weight:700;color:#17048c;font-size:12px;margin-bottom:4px;">'
            'Infection Log</div>'
            '<div style="background:#e2eeff;border-radius:8px;padding:8px;'
            'color:#17048c;opacity:0.6;font-size:10px;font-style:italic;text-align:center;">'
            'No infections yet</div>'
        )

    events = list(reversed(model.transmission_events))[:max_rows]
    rows = []
    for e in events:
        agent_type = e.get("agent_type", "?").title()
        room = e.get("room", "?")
        aid = e.get("agent_id", "?")
        tick = e.get("tick", 0)
        rows.append(
            f'<div style="display:grid;grid-template-columns:46px 1fr;gap:6px;'
            f'font-size:10px;color:#17048c;padding:4px 6px;margin:2px 0;'
            f'background:#fde2e2;border-left:3px solid #EF4444;border-radius:4px;">'
            f'<div style="font-weight:700;color:#17048c;">t={tick}</div>'
            f'<div><b>{agent_type} #{aid}</b> infected in <b>{room}</b></div>'
            f'</div>'
        )
    return (
        '<div style="font-weight:700;color:#17048c;font-size:12px;margin-bottom:4px;">'
        f'Infection Log ({len(model.transmission_events)} total)</div>'
        '<div style="background:#e2eeff;border-radius:8px;padding:4px;'
        'max-height:220px;overflow-y:auto;">'
        + "".join(rows) + '</div>'
    )


def _settings_summary_html(params, floor_plan_name, fp_height=None):
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
def SimulationPage():
    model = model_instance.value
    tick = sim_tick.value
    running = sim_running.value
    paused = sim_paused.value

    live_speed, set_speed = solara.use_state(sim_params.value.get("sim_speed", 10))
    settings_open, set_settings_open = solara.use_state(False)

    def run_loop():
        m = model_instance.value
        if m is None:
            return
        while m.running and sim_running.value:
            if sim_paused.value:
                time.sleep(0.1)
                continue
            m.step()
            sim_tick.set(m.tick_count)
            time.sleep(1.0 / max(1, live_speed))
        sim_running.set(False)
        if m:
            
            res = m.get_results()
            sim_results.set(res)

    thread_started, set_ts = solara.use_state(False)
    if running and not thread_started and model is not None:
        set_ts(True)
        threading.Thread(target=run_loop, daemon=True).start()

    living = model._living_agents() if model else []
    sir_last = model.sir_history[-1] if model and model.sir_history else {}
    s_all = sir_last.get("S", 0)
    i_all = sir_last.get("I", 0)
    r_all = sir_last.get("R", 0)
    est_pop = model.estimated_total_pop if model else 0

    with solara.Column(
        style={"min-height": "100vh", "background": PALETTE["bg"],
                "padding": "20px", "gap": "12px"}
    ):
        
        PageHeader(
            subtitle=f"Simulation — Tick {tick}",
            back_page="settings_params",
            back_label="← Back to Settings",
        )

        
        with solara.Row(
            style={
                "background": PALETTE["card"],
                "padding": "8px 16px",
                "border-radius": "12px",
                "align-items": "center",
                "gap": "16px",
                "flex-wrap": "wrap",
            }
        ):
            state_col = "#d3e65c" if running and not paused else "#cb6ce6"
            state_txt = ("● Running" if running and not paused
                         else "● Paused" if paused else "● Stopped")
            solara.HTML(
                tag="span",
                unsafe_innerHTML=(
                    f'<span style="font-size:14px;color:{state_col};'
                    f'font-weight:700;">{state_txt}</span>'
                ),
            )
            solara.HTML(
                tag="span",
                unsafe_innerHTML=(
                    f'<span style="font-size:12px;color:#17048c;">'
                    f'<span style="color:#22C55E;">S:{s_all}</span> '
                    f'<span style="color:#EF4444;">I:{i_all}</span> '
                    f'<span style="color:#9CA3AF;">R:{r_all}</span> '
                    f'<span style="opacity:0.7;">| In building:{len(living)} '
                    f'| Est. total:{est_pop}</span></span>'
                ),
            )

        with solara.Row(
            style={"flex": "1", "gap": "16px", "background": "transparent",
                    "align-items": "stretch"}
        ):
            #sidebar
            with solara.Column(
                style={
                    "width": "340px",
                    "min-width": "340px",
                    "background": PALETTE["card"],
                    "padding": "16px",
                    "border-radius": "16px",
                    "overflow-y": "auto",
                    "max-height": "86vh",
                    "gap": "12px",
                }
            ):
                
                solara.SliderInt(
                    label=f"Speed — {live_speed} t/s",
                    value=live_speed, min=1, max=60, on_value=set_speed,
                )
                with solara.Row(style={"gap": "6px", "background": "transparent"}):
                    if not paused:
                        solara.Button(
                            label="⏸ Pause",
                            on_click=lambda: sim_paused.set(True),
                            style={"text-transform": "none", "flex": "1",
                                    "background": PALETTE["pink"], "color": "#ffffff",
                                    "border-radius": "10px"},
                        )
                    else:
                        solara.Button(
                            label="▶ Resume",
                            on_click=lambda: sim_paused.set(False),
                            style={"text-transform": "none", "flex": "1",
                                    "background": PALETTE["accent"], "color": PALETTE["text"],
                                    "border-radius": "10px"},
                        )

                    def step_once():
                        m = model_instance.value
                        if m and m.running:
                            sim_paused.set(True)
                            m.step()
                            sim_tick.set(m.tick_count)

                    solara.Button(
                        label="⏭",
                        on_click=step_once,
                        style={"text-transform": "none", "flex": "1",
                                "background": PALETTE["pink"], "color": "#ffffff",
                                "border-radius": "10px"},
                    )

                def stop():
                    sim_running.set(False)
                    sim_paused.set(False)
                    m = model_instance.value
                    if m:
                        m.running = False
                        res = m.get_results()
                        sim_results.set(res)
                        current_page.set("analytics")

                solara.Button(
                    label="⏹ Stop → Results",
                    on_click=stop,
                    style={"text-transform": "none", "width": "100%",
                            "background": PALETTE["primary"], "color": "#ffffff",
                            "border-radius": "10px"},
                )

                # Live SIR chart (new!)
                solara.HTML(
                    tag="div",
                    unsafe_innerHTML=(
                        '<div style="font-weight:700;color:#17048c;font-size:12px;'
                        'margin-bottom:4px;">SIR Curve</div>'
                        f'{_sir_chart_html(model.sir_history if model else [], 290, 150)}'
                    ),
                )

                #Legend
                solara.HTML(tag="div", unsafe_innerHTML=_legend_html())

                #agent counts
                if model:
                    solara.HTML(tag="div", unsafe_innerHTML=_agent_counts_html(model))

                #room contamination
                if model:
                    solara.HTML(tag="div", unsafe_innerHTML=_room_contam_bars_html(model, 10))

                #infection log
                if model:
                    solara.HTML(tag="div", unsafe_innerHTML=_infection_log_html(model, 20))

                #settings summary
                solara.Button(
                    label=("▾ Hide Simulation Settings" if settings_open
                           else "▸ Show Simulation Settings"),
                    on_click=lambda: set_settings_open(not settings_open),
                    style={
                        "text-transform": "none",
                        "background": "#e2eeff",
                        "color": PALETTE["text"],
                        "border-radius": "10px",
                        "font-weight": "700",
                        "font-size": "11px",
                        "width": "100%",
                        "padding": "8px",
                    },
                )
                if settings_open:
                    params = model.p if model else sim_params.value
                    fp_name = model.floor_plan.name if model else sim_params.value.get("floor_plan_name", "")
                    fp_h = model.floor_plan.height if model else None
                    solara.HTML(
                        tag="div",
                        unsafe_innerHTML=_settings_summary_html(params, fp_name, fp_height=fp_h),
                    )

            #Floor plan 
            with solara.Column(
                style={
                    "flex": "1",
                    "display": "flex",
                    "align-items": "center",
                    "justify-content": "center",
                    "background": PALETTE["card"],
                    "border-radius": "16px",
                    "padding": "10px",
                }
            ):
                solara.HTML(tag="div", unsafe_innerHTML=_render_fp(model, 780, 520))
