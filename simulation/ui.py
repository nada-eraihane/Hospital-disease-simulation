import solara

PALETTE = {
    "bg":       "#e2eeff",   
    "card":     "#b1d2ff",   
    "primary":  "#17048c",   
    "inner":    "#17048c",   
    "accent":   "#d3e65c",   
    "pink":     "#cb6ce6",   
    "text_on_primary": "#ffffff",
    "text":     "#17048c",
}


def page_header_html(subtitle=None, back_label=None):

    extra = ''
    if subtitle:
        extra = (
            f'<span style="color:#b1d2ff;font-size:14px;font-weight:500;'
            f'margin-left:16px;">— {subtitle}</span>'
        )
    return (
        f'<span style="font-size:22px;margin:6px 20px;font-weight:700;'
        f'color:#F8FAFC;letter-spacing:-0.5px;"> Hospital Simulation</span>'
        f'{extra}'
    )


@solara.component
def PageHeader(subtitle: str = None, back_page: str = None, back_label: str = "← Back"):
    
    from state import current_page

    with solara.Row(
        style={
            "background": PALETTE["primary"],
            "padding": "12px 28px",
            "align-items": "center",
            "border-radius": "14px",
            "gap": "16px",
        }
    ):
        if back_page:
            solara.Button(
                label=back_label,
                on_click=lambda: current_page.set(back_page),
                style={
                    "text-transform": "none",
                    "background": PALETTE["accent"],
                    "color": PALETTE["text"],
                    "border-radius": "20px",
                    "padding": "6px 18px",
                    "font-weight": "700",
                    "font-size": "13px",
                },
            )
        solara.HTML(
            tag="div",
            unsafe_innerHTML=page_header_html(subtitle),
        )
