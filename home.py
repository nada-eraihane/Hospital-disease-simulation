import solara
from state import current_page, saved_results


@solara.component
def HomePage():
    has_results = len(saved_results.value) > 0

    def open_previous():
        if not has_results:
            return
        current_page.set("previous")

    with solara.Column(style={"min-height": "100vh", "background": "#e2eeff", "padding": "20px"}):
      
        with solara.Row(
            style={
                "background": "#17048c",
                "padding": "16px 32px",
                "align-items": "center",
                "border-radius": "12px",
            }
        ):
            solara.HTML(
                tag="div",
                unsafe_innerHTML='<span style="font-size:24px; margin: 20px; font-weight:700; color:#F8FAFC; letter-spacing:-0.5px;">🏥 Hospital Simulation</span>',
            )

        
        with solara.Row(
            style={
                "background": "transparent",
                "flex": "1",
                "padding": "48px",
                "gap": "48px",
                "align-items": "center",
                "justify-content": "center",
                "min-height": "80vh",
            }
        ):
            
            with solara.Column(
                style={
                    "background": "transparent",
                    "flex": "1",
                    "max-width": "560px",
                    "gap": "24px",
                }
            ):
                solara.HTML(
                    tag="div",
                    unsafe_innerHTML="""
                    <h1 style="background: transparent; font-size:48px; font-weight:800; color:#17048c; line-height:1.1; margin:0;">
                        Hospital Infection<br/>
                        <span style="background: linear-gradient(135deg, #b1d2ff, #004aad); -webkit-background-clip:text; -webkit-text-fill-color:transparent;">
                            Simulation Engine
                        </span>
                    </h1>
                    """,
                )

                
                with solara.Column(style={"background": "transparent", "gap": "12px",
                                           "margin-top": "16px"}):
                    solara.Button(
                        label="New Simulation",
                        on_click=lambda: current_page.set("settings_fp"),
                        color="#cb6ce6",
                        style={
                            "width": "280px",
                            "height": "52px",
                            "font-size": "16px",
                            "font-weight": "600",
                            "border-radius": "12px",
                            "text-transform": "none",
                        },
                    )

                    if has_results:
                        solara.Button(
                            label=f"Previous Simulations ({len(saved_results.value)})",
                            on_click=open_previous,
                            style={
                                "width": "280px",
                                "height": "52px",
                                "font-size": "16px",
                                "font-weight": "600",
                                "border-radius": "12px",
                                "text-transform": "none",
                                "background": "#1E293B",
                                "color": "#ffffff",
                                "cursor": "pointer",
                            },
                        )
                    else:
                        solara.Button(
                            label="Previous Simulations",
                            on_click=lambda: None,
                            style={
                                "width": "280px",
                                "height": "52px",
                                "font-size": "16px",
                                "font-weight": "600",
                                "border-radius": "12px",
                                "text-transform": "none",
                                "background": "#1E293B",
                                "color": "#ffffff",
                                "opacity": "0.5",
                                "cursor": "default",
                            },
                        )

            
            with solara.Column(
                style={
                    "flex": "1",
                    "max-width": "480px",
                    "align-items": "center",
                    "justify-content": "center",
                }
            ):
                solara.HTML(
                    tag="div",
                    unsafe_innerHTML="""
                    <div style="
                        width: 520px; height: 320px;
                        background: linear-gradient(135deg, #cb6ce6, #d3e65c);
                        border-radius: 24px;
                        display: flex; align-items: center; justify-content: center;
                        position: relative; overflow: hidden;
                    ">
                        <div style="text-align:center; z-index:1;">
                            <div style="font-size:80px; margin-bottom:16px;">🏥</div>
                            <div style="font-size:16px; color:#17048c; font-weight:500;">
                                Agent-Based Disease Modelling
                            </div>
                            <div style="margin-top:20px; display:flex; gap:8px; justify-content:center;">
                                <span style="display:inline-block; width:12px; height:12px; border-radius:50%; background:#22C55E;"></span>
                                <span style="font-size:12px; color:#17048c;">S</span>
                                <span style="display:inline-block; width:12px; height:12px; border-radius:50%; background:#EF4444; margin-left:8px;"></span>
                                <span style="font-size:12px; color:#17048c;">I</span>
                                <span style="display:inline-block; width:12px; height:12px; border-radius:50%; background:#9CA3AF; margin-left:8px;"></span>
                                <span style="font-size:12px; color:#17048c;">R</span>
                            </div>
                        </div>
                        <div style="
                            position:absolute; top:-60px; right:-60px;
                            width:200px; height:200px; border-radius:50%;
                            background: radial-gradient(circle, rgba(59,130,246,0.15) 0%, transparent 70%);
                        "></div>
                        <div style="
                            position:absolute; bottom:-40px; left:-40px;
                            width:160px; height:160px; border-radius:50%;
                            background: radial-gradient(circle, rgba(139,92,246,0.1) 0%, transparent 70%);
                        "></div>
                    </div>
                    """,
                )
