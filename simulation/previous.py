import solara
from state import current_page, saved_results, sim_results
from ui import PALETTE, PageHeader


@solara.component
def PreviousPage():
    results = saved_results.value

    with solara.Column(
        style={"min-height": "100vh", "background": PALETTE["bg"],
                "padding": "20px", "gap": "14px"}
    ):
        PageHeader(subtitle="Previous Simulations", back_page="home", back_label="← Home")

        if not results:
            solara.HTML(
                tag="div",
                unsafe_innerHTML=(
                    f'<div style="color:{PALETTE["text"]};opacity:0.6;padding:48px;'
                    f'text-align:center;background:{PALETTE["card"]};'
                    f'border-radius:16px;font-size:14px;">'
                    f'No saved results yet. Run a simulation and press '
                    f'<b>Save</b> on the results page.</div>'
                ),
            )
            return

        with solara.Column(style={"gap": "12px", "background": "transparent"}):
            for idx in range(len(results) - 1, -1, -1):
                res = results[idx]
                sir = res.get("sir_history", [])
                final = sir[-1] if sir else {"S": 0, "I": 0, "R": 0}
                ticks = res.get("tick_count", 0)
                fp_name = res.get("floor_plan_name", "?")
                ts = res.get("timestamp", "")
                infections = len(res.get("transmission_events", []))
                params = res.get("params", {})

                def view_it(r=res):
                    sim_results.set(r)
                    current_page.set("analytics")

                with solara.Row(
                    style={
                        "background": PALETTE["card"],
                        "border-radius": "14px",
                        "padding": "16px 20px",
                        "gap": "16px",
                        "align-items": "center",
                    }
                ):

                    solara.HTML(
                        tag="div",
                        unsafe_innerHTML=(
                            f'<div style="color:{PALETTE["text"]};">'
                            f'<div style="font-size:18px;font-weight:700;">Run #{idx + 1}</div>'
                            f'<div style="font-size:11px;opacity:0.7;">{ts}</div>'
                            f'</div>'
                        ),
                    )

                    solara.HTML(
                        tag="div",
                        unsafe_innerHTML=(
                            f'<div style="flex:1;color:{PALETTE["text"]};font-size:13px;">'
                            f'<b>{fp_name}</b> · {ticks} ticks · '
                            f'<span style="color:#EF4444;">{infections} total infections</span> · '
                            f'{params.get("num_patients", 0)}P · '
                            f'{params.get("num_doctors", 0)}D · '
                            f'{params.get("num_nurses", 0)}N'
                            f'<br/>'
                            f'<span style="color:#22C55E;">S:{final.get("S",0)}</span> '
                            f'<span style="color:#EF4444;">I:{final.get("I",0)}</span> '
                            f'<span style="color:#9CA3AF;">R:{final.get("R",0)}</span>'
                            f'</div>'
                        ),
                    )

                    solara.Button(
                        label="View Results →",
                        on_click=view_it,
                        style={
                            "text-transform": "none",
                            "background": PALETTE["primary"],
                            "color": "#ffffff",
                            "border-radius": "20px",
                            "padding": "10px 20px",
                            "font-weight": "700",
                        },
                    )
