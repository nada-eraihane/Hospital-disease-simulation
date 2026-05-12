
import solara
from persistence import load_all_runs

current_page = solara.reactive("home")

sim_params = solara.reactive({
    "num_doctors": 2, 
    "num_nurses": 4, 
    "num_cleaners": 2, 
    "num_volunteers": 2,
    "num_patients": 12, 
    "num_initially_infected": 2,
    "patient_arrival_interval": 15, 
    "infected_arrival_fraction": 0.1,
    "visiting_hours_start": 100, 
    "visiting_hours_end": 300,
    "visitor_arrival_interval": 20,
    "quanta_rate": 25.0, 
    "near_field_radius": 1.5, 
    "random_air_speed": 5.0,
    "recovery_rate": 0.003, 
    "mask_efficiency": 0.0, 
    "hepa_cadr": 300.0,
    "delta_t": 0.05, 
    "sim_speed": 10, 
    "max_steps": 1000,
    "random_seed": 42, 
    "floor_plan_name": "medium",
})

custom_floor_plan = solara.reactive(None)
model_instance = solara.reactive(None)
sim_running = solara.reactive(False)
sim_paused = solara.reactive(False)
sim_tick = solara.reactive(0)
sim_results = solara.reactive(None)
sim_sir_history = solara.reactive([])


try:
    _initial_results, _initial_plans = load_all_runs()
except Exception:
    _initial_results, _initial_plans = [], {}

saved_results = solara.reactive(_initial_results)

saved_floor_plans = solara.reactive(_initial_plans)
