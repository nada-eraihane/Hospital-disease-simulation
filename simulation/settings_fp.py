import solara
import json
from state import current_page, sim_params, custom_floor_plan
from floorplan import FloorPlan, load_predefined
from ui import PALETTE, PageHeader


FLOOR_PLAN_EDITOR_URL = "/static/public/floorplaneditor.html"


def _render_preview_svg(fp, width=560, height=420):
    
    if fp is None:
        return (
            f'<svg width="{width}" height="{height}">'
            f'<rect width="{width}" height="{height}" fill="{PALETTE["primary"]}" rx="12"/>'
            f'<text x="{width//2}" y="{height//2}" fill="#e2eeff" '
            f'text-anchor="middle" font-family="sans-serif">floor plan preview</text>'
            f'</svg>'
        )

    sx = width / fp.width
    sy = height / fp.height
    scale = min(sx, sy) * 0.92
    ox = (width - fp.width * scale) / 2
    oy = (height - fp.height * scale) / 2

    def tx(x): return ox + x * scale
    def ty(y): return oy + y * scale
    def ts(v): return v * scale

    _ABBR = [("Pa","patient"),("Dr","doctor"),("Nu","nurse"),
             ("Vi","visitor"),("Cl","cleaner"),("Vo","volunteer")]

    parts = [
        f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" '
        f'style="background:#e2eeff;border-radius:12px;">'
    ]
    parts.append(
        f'<rect x="{tx(0)}" y="{ty(0)}" width="{fp.width*scale}" '
        f'height="{fp.height*scale}" fill="#e2eeff" rx="4"/>'
    )

    for r in fp.rooms:
        pts = " ".join(f"{tx(p[0])},{ty(p[1])}" for p in r.polygon)
        parts.append(
            f'<polygon points="{pts}" fill="#b1d2ff" stroke="#17048c" stroke-width="1"/>'
        )
        cx = sum(p[0] for p in r.polygon) / len(r.polygon)
        cy = sum(p[1] for p in r.polygon) / len(r.polygon)
        no_access = " ".join(a for a, t in _ABBR if t not in r.access)
        parts.append(
            f'<text x="{tx(cx)}" y="{ty(cy)-7}" fill="#17048c" font-size="9" '
            f'text-anchor="middle" font-family="monospace" font-weight="bold">{r.name}</text>'
        )
        parts.append(
            f'<text x="{tx(cx)}" y="{ty(cy)+3}" fill="#17048c" font-size="7" '
            f'text-anchor="middle" font-family="monospace" opacity="0.7">'
            f'{r.ventilation_ach:.0f} ACH · {r.volume_m3:.0f}m³</text>'
        )
        if no_access:
            parts.append(
                f'<text x="{tx(cx)}" y="{ty(cy)+13}" fill="#EF4444" font-size="7" '
                f'text-anchor="middle" font-family="monospace" font-weight="bold">'
                f'✗ {no_access}</text>'
            )

    for w in fp.walls:
        parts.append(
            f'<line x1="{tx(w[0][0])}" y1="{ty(w[0][1])}" '
            f'x2="{tx(w[1][0])}" y2="{ty(w[1][1])}" stroke="#17048c" stroke-width="2"/>'
        )

    for b in fp.beds:
        bx, by = b.position
        parts.append(
            f'<rect x="{tx(bx)-ts(4)}" y="{ty(by)-ts(3)}" '
            f'width="{ts(8)}" height="{ts(6)}" fill="#004aad" rx="1" opacity="0.7"/>'
        )
    for d in fp.doors:
        parts.append(
            f'<circle cx="{tx(d.position[0])}" cy="{ty(d.position[1])}" '
            f'r="{ts(3)}" fill="{PALETTE["pink"]}" opacity="0.9"/>'
        )
    for e in fp.entrances:
        parts.append(
            f'<circle cx="{tx(e.position[0])}" cy="{ty(e.position[1])}" '
            f'r="{ts(7)}" fill="none" stroke="{PALETTE["accent"]}" stroke-width="2"/>'
        )

    parts.append('</svg>')
    return "\n".join(parts)


@solara.component
def FloorPlanPage():
    error_msg, set_error = solara.use_state("")
    selected, set_selected = solara.use_state(sim_params.value.get("floor_plan_name", "medium"))

    try:
        if custom_floor_plan.value:
            preview_fp = FloorPlan.from_dict(custom_floor_plan.value)
        else:
            preview_fp = load_predefined(selected)
    except Exception:
        preview_fp = None

    OUTER_CARD = {
        "background": PALETTE["card"],
        "border-radius": "20px",
        "padding": "20px",
        "gap": "16px",
    }
    INNER_CARD = {
        "background": PALETTE["inner"],
        "border-radius": "16px",
        "padding": "20px",
        "gap": "12px",
    }

    with solara.Column(
        style={"min-height": "100vh", "background": PALETTE["bg"],
                "padding": "20px", "gap": "16px"}
    ):
        # Shared page header
        PageHeader(subtitle="Floor Plan", back_page="home", back_label="← Home")

        # Step caption
        solara.HTML(
            tag="div",
            unsafe_innerHTML=(
                '<div style="text-align:center;color:#17048c;font-size:16px;'
                'font-weight:600;margin-top:-4px;">'
                'Simulation Settings for floor plan</div>'
            ),
        )

        with solara.Row(style={"gap": "20px", "background": "transparent",
                                "align-items": "stretch"}):
            # ── LEFT COLUMN ──
            with solara.Column(style={**OUTER_CARD, "flex": "1", "min-width": "400px"}):
                # Preset picker
                with solara.Column(style=INNER_CARD):
                    solara.HTML(
                        tag="div",
                        unsafe_innerHTML=(
                            '<div style="color:#ffffff;font-size:18px;font-weight:600;'
                            'text-align:center;margin-bottom:8px;">'
                            'Select a predefined floor plan</div>'
                        ),
                    )

                    def pick(name):
                        set_selected(name)
                        custom_floor_plan.set(None)
                        set_error("")

                    with solara.Row(style={"gap": "12px", "background": "transparent",
                                            "justify-content": "space-around"}):
                        for key, label in [("simple", "simple"), ("medium", "medium"),
                                           ("complex", "complex")]:
                            is_active = (selected == key) and (custom_floor_plan.value is None)
                            solara.Button(
                                label=label,
                                on_click=lambda k=key: pick(k),
                                style={
                                    "text-transform": "none",
                                    "background": PALETTE["accent"] if is_active
                                                  else PALETTE["card"],
                                    "color": PALETTE["text"],
                                    "border-radius": "22px",
                                    "padding": "8px 32px",
                                    "font-weight": "700" if is_active else "500",
                                    "flex": "1",
                                    "min-width": "100px",
                                    "border": (f'2px solid {PALETTE["accent"]}'
                                               if is_active else '2px solid transparent'),
                                },
                            )

               
                with solara.Column(style=INNER_CARD):
                    solara.HTML(
                        tag="div",
                        unsafe_innerHTML=(
                            '<div style="color:#ffffff;font-size:18px;font-weight:600;'
                            'text-align:center;margin-bottom:8px;">'
                            'Floor plan file drag and drop zone</div>'
                        ),
                    )

                    def on_upload(file_info):
                        try:
                            content = file_info["data"]
                            if isinstance(content, bytes):
                                content = content.decode("utf-8")
                            parsed = json.loads(content)
                            if "rooms" not in parsed or "walls" not in parsed:
                                set_error("JSON missing 'rooms' or 'walls'.")
                                return
                            custom_floor_plan.set(parsed)
                            set_error("")
                        except Exception as e:
                            set_error(f"Invalid file: {e}")

                    with solara.Column(style={
                        "background": PALETTE["card"],
                        "border-radius": "14px",
                        "padding": "24px",
                        "align-items": "center",
                        "gap": "8px",
                    }):
                        solara.HTML(
                            tag="div",
                            unsafe_innerHTML=(
                                '<div style="text-align:center;font-size:56px;'
                                'color:#17048c;opacity:0.9;">📄</div>'
                            ),
                        )
                        solara.FileDrop(
                            label="Drop a floor-plan JSON here",
                            on_file=on_upload,
                            lazy=False,
                        )

                    if error_msg:
                        solara.HTML(
                            tag="div",
                            unsafe_innerHTML=(
                                f'<div style="color:{PALETTE["accent"]};font-size:12px;'
                                f'margin-top:6px;text-align:center;">{error_msg}</div>'
                            ),
                        )

                    
                    solara.v.Btn(
                        href=FLOOR_PLAN_EDITOR_URL,
                        target="_blank",
                        block=True,
                        children=["create own floor plan"],
                        style_=(
                            f"background:{PALETTE['accent']};color:{PALETTE['text']};"
                            f"border-radius:22px;padding:12px 24px;font-weight:700;"
                            f"font-size:14px;text-transform:none;"
                        ),
                    )

            
            with solara.Column(style={**OUTER_CARD, "flex": "1", "min-width": "400px"}):
                with solara.Column(style={**INNER_CARD, "height": "100%",
                                           "align-items": "center",
                                           "justify-content": "center"}):
                    solara.HTML(
                        tag="div",
                        unsafe_innerHTML=(
                            '<div style="color:#ffffff;font-size:18px;font-weight:600;'
                            'margin-bottom:12px;text-align:center;">floor plan preview</div>'
                        ),
                    )
                    svg = _render_preview_svg(preview_fp, width=560, height=420)
                    solara.HTML(tag="div", unsafe_innerHTML=svg)

                    if preview_fp:
                        wards = len([r for r in preview_fp.rooms
                                     if r.room_type in ("ward", "icu")])
                        solara.HTML(
                            tag="div",
                            unsafe_innerHTML=(
                                f'<div style="color:#ffffff;font-size:12px;margin-top:8px;'
                                f'text-align:center;opacity:0.85;">'
                                f'<b>{preview_fp.name}</b> — '
                                f'{len(preview_fp.rooms)} rooms · {wards} wards/ICU · '
                                f'{len(preview_fp.beds)} beds · {len(preview_fp.doors)} doors'
                                f'</div>'
                            ),
                        )

        
        def go_next():
            p = sim_params.value.copy()
            p["floor_plan_name"] = selected
            sim_params.set(p)
            current_page.set("settings_params")

        with solara.Row(style={"background": "transparent", "margin-top": "4px"}):
            solara.Button(
                label="Next  →",
                on_click=go_next,
                style={
                    "text-transform": "none",
                    "background": PALETTE["primary"],
                    "color": "#ffffff",
                    "width": "100%",
                    "height": "56px",
                    "border-radius": "30px",
                    "font-size": "18px",
                    "font-weight": "700",
                },
            )
