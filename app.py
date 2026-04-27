"""
app.py — Main page router.
"""
import solara
from state import current_page
from home import HomePage
from settings_fp import FloorPlanPage
from settings_params import ParamsPage
from simulation import SimulationPage
from analytics import AnalyticsPage
from previous import PreviousPage


@solara.component
def Page():
    p = current_page.value
    if p == "home":
        HomePage()
    elif p == "settings_fp":
        FloorPlanPage()
    elif p == "settings_params":
        ParamsPage()
    elif p == "simulation":
        SimulationPage()
    elif p == "analytics":
        AnalyticsPage()
    elif p == "previous":
        PreviousPage()
    else:
        HomePage()
