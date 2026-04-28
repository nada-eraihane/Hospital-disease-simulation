import solara
from state import (
    current_page, sim_params, custom_floor_plan,
    model_instance, sim_running, sim_paused, sim_tick, sim_results,
)
from floorplan import FloorPlan, load_predefined
from model import HospitalModel
from ui import PALETTE, PageHeader


def _update(key, val):
    p = sim_params.value.copy()
    p[key] = val
    sim_params.set(p)


def _analyse_floor_plan(fp):
    
    wards = [r for r in fp.rooms if r.room_type in ("ward", "icu")]
    beds = len(fp.beds)
    offices = [r for r in fp.rooms if r.room_type == "office"]
    specials = [r for r in fp.rooms if r.room_type in ("special", "procedure")]
    return {
        "num_wards": len(wards),
        "num_beds": beds,
        "num_offices": len(offices),
        "num_specials": len(specials),
        "suggested_doctors": max(2, len(wards) + len(specials)),
        "suggested_nurses": max(2, len(wards) * 2),
        "suggested_patients": min(beds, max(8, beds // 2)),
        "suggested_cleaners": max(1, len(fp.rooms) // 5),
    }


@solara.component
def ParamsPage():
    p = sim_params.value

    try:
        fp_data = custom_floor_plan.value
        fp = (FloorPlan.from_dict(fp_data) if fp_data
              else load_predefined(p.get("floor_plan_name", "medium")))
    except Exception:
        fp = None
    analysis = _analyse_floor_plan(fp) if fp else {}

    # One-shot: auto-apply suggestions the first time the page loads
    suggested, set_suggested = solara.use_state(False)
    if not suggested and analysis:
        set_suggested(True)
        _update("num_doctors", analysis["suggested_doctors"])
        _update("num_nurses", analysis["suggested_nurses"])
        _update("num_patients", analysis["suggested_patients"])
        _update("num_cleaners", analysis["suggested_cleaners"])

    CARD = {
        "background": PALETTE["card"],
        "border-radius": "14px",
        "padding": "20px",
        "gap": "10px",
    }

    def heading(txt):
        return (f'<div style="color:#17048c;font-weight:700;font-size:15px;'
                f'margin-bottom:4px;">{txt}</div>')

    with solara.Column(
        style={"min-height": "100vh", "background": PALETTE["bg"],
                "padding": "20px", "gap": "14px"}
    ):
        solara.HTML(
            tag="style",
            unsafe_innerHTML=(
                ".v-label,.v-messages__message,.v-slider-thumb__label span"
                "{color:#17048c !important;}"
            ),
        )
        PageHeader(subtitle="Parameters", back_page="settings_fp", back_label="← Floor Plan")

        if analysis:
            solara.HTML(
                tag="div",
                unsafe_innerHTML=(
                    f'<div style="color:#17048c;font-size:13px;padding:12px 16px;'
                    f'background:#b1d2ff;border-radius:12px;">'
                    f'Floor plan has <b>{analysis["num_wards"]} wards/ICU</b>, '
                    f'<b>{analysis["num_beds"]} beds</b>, '
                    f'<b>{analysis["num_offices"]} offices</b>, '
                    f'<b>{analysis["num_specials"]} procedure rooms</b>. '
                    f'Values below are auto-suggested — adjust freely.</div>'
                ),
            )

        with solara.Row(style={"gap": "16px", "flex-wrap": "wrap",
                                "background": "transparent"}):
            # ── LEFT COLUMN ──
            with solara.Column(style={"flex": "1", "min-width": "380px",
                                       "gap": "14px", "background": "transparent"}):
                with solara.Column(style=CARD):
                    solara.HTML(tag="div", unsafe_innerHTML=heading("Population"))
                    solara.SliderInt(
                        label=f"Patients — {p['num_patients']} (beds: {analysis.get('num_beds', 0)})",
                        value=p["num_patients"], min=1,
                        max=max(50, analysis.get("num_beds", 50)),
                        on_value=lambda v: _update("num_patients", v),
                    )
                    solara.SliderInt(label=f"Doctors — {p['num_doctors']}",
                                      value=p["num_doctors"], min=1, max=30,
                                      on_value=lambda v: _update("num_doctors", v))
                    solara.SliderInt(label=f"Nurses — {p['num_nurses']}",
                                      value=p["num_nurses"], min=1, max=50,
                                      on_value=lambda v: _update("num_nurses", v))
                    solara.SliderInt(label=f"Cleaners — {p['num_cleaners']}",
                                      value=p["num_cleaners"], min=0, max=20,
                                      on_value=lambda v: _update("num_cleaners", v))
                    solara.SliderInt(label=f"Volunteers — {p['num_volunteers']}",
                                      value=p["num_volunteers"], min=0, max=20,
                                      on_value=lambda v: _update("num_volunteers", v))
                    solara.SliderInt(
                        label=f"Initially infected — {p['num_initially_infected']}",
                        value=p["num_initially_infected"], min=1, max=20,
                        on_value=lambda v: _update("num_initially_infected", v),
                    )

                with solara.Column(style=CARD):
                    solara.HTML(tag="div", unsafe_innerHTML=heading("Patient Arrivals"))
                    solara.SliderInt(
                        label=f"Arrival interval — {p['patient_arrival_interval']} ticks",
                        value=p["patient_arrival_interval"], min=5, max=100,
                        on_value=lambda v: _update("patient_arrival_interval", v),
                    )
                    solara.SliderFloat(
                        label=f"Infected on arrival — {p['infected_arrival_fraction']:.0%}",
                        value=p["infected_arrival_fraction"], min=0.0, max=0.5, step=0.01,
                        on_value=lambda v: _update("infected_arrival_fraction", v),
                    )

                with solara.Column(style=CARD):
                    solara.HTML(tag="div", unsafe_innerHTML=heading("Visitors"))
                    solara.SliderInt(
                        label=f"Visiting start — tick {p['visiting_hours_start']}",
                        value=p["visiting_hours_start"], min=0, max=500,
                        on_value=lambda v: _update("visiting_hours_start", v),
                    )
                    solara.SliderInt(
                        label=f"Visiting end — tick {p['visiting_hours_end']}",
                        value=p["visiting_hours_end"], min=50, max=1000,
                        on_value=lambda v: _update("visiting_hours_end", v),
                    )
                    solara.SliderInt(
                        label=f"Visitor interval — {p['visitor_arrival_interval']} ticks",
                        value=p["visitor_arrival_interval"], min=5, max=100,
                        on_value=lambda v: _update("visitor_arrival_interval", v),
                    )

            # ── RIGHT COLUMN ──
            with solara.Column(style={"flex": "1", "min-width": "380px",
                                       "gap": "14px", "background": "transparent"}):
                with solara.Column(style=CARD):
                    solara.HTML(tag="div",
                                 unsafe_innerHTML=heading("Pathogen (Wells-Riley)"))
                    solara.SliderFloat(
                        label=f"Quanta rate — {p['quanta_rate']:.0f} q/h",
                        value=p["quanta_rate"], min=1, max=200, step=1,
                        on_value=lambda v: _update("quanta_rate", v),
                    )
                    solara.SliderFloat(
                        label=f"Near-field radius — {p['near_field_radius']:.1f} m",
                        value=p["near_field_radius"], min=0.5, max=3.0, step=0.1,
                        on_value=lambda v: _update("near_field_radius", v),
                    )
                    solara.SliderFloat(
                        label=f"Air speed — {p['random_air_speed']:.1f} m/min",
                        value=p["random_air_speed"], min=1, max=15, step=0.5,
                        on_value=lambda v: _update("random_air_speed", v),
                    )
                    solara.SliderFloat(
                        label=f"Recovery rate — {p['recovery_rate']:.3f} /tick",
                        value=p["recovery_rate"], min=0.001, max=0.05, step=0.001,
                        on_value=lambda v: _update("recovery_rate", v),
                    )

                with solara.Column(style=CARD):
                    solara.HTML(tag="div", unsafe_innerHTML=heading("Interventions"))
                    solara.SliderFloat(
                        label=f"Mask efficiency — {p['mask_efficiency']:.0%}",
                        value=p["mask_efficiency"], min=0, max=0.95, step=0.05,
                        on_value=lambda v: _update("mask_efficiency", v),
                    )
                    solara.SliderFloat(
                        label=f"HEPA CADR — {p['hepa_cadr']:.0f} m³/h",
                        value=p["hepa_cadr"], min=0, max=600, step=10,
                        on_value=lambda v: _update("hepa_cadr", v),
                    )

                with solara.Column(style=CARD):
                    solara.HTML(tag="div", unsafe_innerHTML=heading("Simulation Control"))
                    solara.SliderFloat(
                        label=f"Timestep — {p['delta_t']:.2f} h ({p['delta_t']*60:.0f} min/tick)",
                        value=p["delta_t"], min=0.01, max=0.2, step=0.01,
                        on_value=lambda v: _update("delta_t", v),
                    )
                    solara.SliderInt(
                        label=f"Speed — {p['sim_speed']} ticks/s",
                        value=p["sim_speed"], min=1, max=60,
                        on_value=lambda v: _update("sim_speed", v),
                    )
                    solara.SliderInt(
                        label=f"Max steps — {p['max_steps']}",
                        value=p["max_steps"], min=100, max=5000, step=100,
                        on_value=lambda v: _update("max_steps", v),
                    )
                    solara.SliderInt(
                        label=f"Seed — {p['random_seed']}",
                        value=p["random_seed"], min=0, max=9999,
                        on_value=lambda v: _update("random_seed", v),
                    )

        def run_sim():
            params = sim_params.value.copy()
            fp_data = custom_floor_plan.value
            fp_obj = (FloorPlan.from_dict(fp_data)
                      if fp_data else load_predefined(params.get("floor_plan_name", "medium")))
            model = HospitalModel(params, fp_obj)
            model_instance.set(model)
            sim_tick.set(0)
            sim_running.set(True)
            sim_paused.set(False)
            sim_results.set(None)
            current_page.set("simulation")

        with solara.Row(
            style={"justify-content": "flex-end", "margin-top": "6px",
                    "background": "transparent", "gap": "12px"}
        ):
            solara.Button(
                label="← Back",
                on_click=lambda: current_page.set("settings_fp"),
                style={
                    "height": "52px",
                    "font-size": "14px",
                    "border-radius": "20px",
                    "text-transform": "none",
                    "background": PALETTE["card"],
                    "color": PALETTE["text"],
                    "padding": "0 28px",
                    "font-weight": "600",
                },
            )
            solara.Button(
                label="▶ Run Simulation",
                on_click=run_sim,
                style={
                    "height": "52px",
                    "font-size": "16px",
                    "font-weight": "700",
                    "border-radius": "20px",
                    "text-transform": "none",
                    "padding": "0 40px",
                    "background": PALETTE["primary"],
                    "color": "#ffffff",
                },
            )
