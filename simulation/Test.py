import sys, os, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest
from floorplan import (
    FloorPlan, Room, load_predefined, _wall_crosses, GridPathfinder
)
from agents import (
    HospitalAgent, PatientAgent, DoctorAgent, NurseAgent,
    VisitorAgent, CleanerAgent, VolunteerAgent, Status
)
from model import HospitalModel



BASE_PARAMS = {
    "num_doctors": 1, "num_nurses": 2, "num_cleaners": 1, "num_volunteers": 1,
    "num_patients": 4, "num_initially_infected": 1,
    "quanta_rate": 25.0, "near_field_radius": 1.5,
    "recovery_rate": 0.01, "mask_efficiency": 0.0,
    "hepa_cadr": 300.0, "delta_t": 0.05, "max_steps": 200,
    "random_seed": 42, "floor_plan_name": "simple",
    "patient_arrival_interval": 9999,   
    "visitor_arrival_interval": 9999,
}

@pytest.fixture
def simple_fp():
    return load_predefined("simple")

@pytest.fixture
def medium_fp():
    return load_predefined("medium")

@pytest.fixture
def model():
    m = HospitalModel(dict(BASE_PARAMS))
    return m



# SECTION 1 — UNIT TESTS


class TestWallCrossing:
    

    def test_direct_crossing(self):
        
        wall = ((0, 100), (200, 100))
        assert _wall_crosses((100, 80), (100, 120), wall) is True

    def test_parallel_no_cross(self):
        
        wall = ((0, 100), (200, 100))
        assert _wall_crosses((0, 80), (200, 80), wall) is False

    def test_corner_is_blocked(self):
        
        wall_h = ((0, 100), (200, 100))   # horizontal, ends at corner
        wall_v = ((200, 100), (200, 0))   # vertical,   starts at corner
        move_a = (180, 120)
        move_b = (220, 80)
        blocked_by_h = _wall_crosses(move_a, move_b, wall_h)
        blocked_by_v = _wall_crosses(move_a, move_b, wall_v)
        assert blocked_by_h or blocked_by_v, \
            "Diagonal through a wall corner must be blocked by at least one wall"

    def test_door_gap_is_passable(self):
       
        left_stub  = ((0, 100), (92, 100))
        right_stub = ((108, 100), (200, 100))
        move_a = (100, 80)
        move_b = (100, 120)
        assert _wall_crosses(move_a, move_b, left_stub)  is False
        assert _wall_crosses(move_a, move_b, right_stub) is False


class TestRoomGeometry:


    def test_point_inside_room(self):
        r = Room("Test", "ward", [[0,0],[100,0],[100,100],[0,100]])
        assert r.contains((50, 50)) is True

    def test_point_outside_room(self):
        r = Room("Test", "ward", [[0,0],[100,0],[100,100],[0,100]])
        assert r.contains((150, 50)) is False

    def test_q_ventilation_calculation(self):
        #q_ventilation = ventilation_ach * volume_m3
        r = Room("Test", "ward", [[0,0],[100,0],[100,100],[0,100]],
                 ventilation_ach=6.0, volume_m3=100.0)
        assert r.q_ventilation == pytest.approx(600.0)


class TestFloorPlanLoading:

    def test_simple_loads(self):
        fp = load_predefined("simple")
        assert len(fp.rooms) > 0
        assert len(fp.walls) > 0
        assert len(fp.entrances) > 0

    def test_medium_loads(self):
        fp = load_predefined("medium")
        assert any(r.room_type == "ward" for r in fp.rooms)
        assert any(r.room_type == "icu"  for r in fp.rooms)

    def test_complex_loads(self):
        fp = load_predefined("complex")
        assert len(fp.rooms) >= 15


class TestDiseaseStepMechanics:
    

    def _make_model_no_arrivals(self, extra=None):
        p = dict(BASE_PARAMS)
        if extra:
            p.update(extra)
        return HospitalModel(p)

    def test_near_field_selected_over_far_field_when_higher(self):
        
        def run_and_get_dose(close):
            params = dict(BASE_PARAMS)
            params.update({"recovery_rate": 0.0, 
                           "random_seed": 42,
                           "num_initially_infected": 1})
            m = HospitalModel(params)
            living = m._living_agents()

            
            inf_agent = next(
                (a for a in living
                 if a.status == Status.INFECTED and a.current_room_name),
                None
            )
            sus_agent = next(
                (a for a in living
                 if a.status == Status.SUSCEPTIBLE and isinstance(a, PatientAgent)),
                None
            )
            if inf_agent is None or sus_agent is None:
                return None

            room_name = inf_agent.current_room_name
            sus_agent.current_room_name = room_name

            ix, iy = inf_agent.pos if inf_agent.pos else (100.0, 100.0)
            if close:
                sus_agent.pos = (ix + 0.5, iy + 0.5)   # within near-field radius
            else:
                sus_agent.pos = (ix + 50.0, iy + 50.0)  # outside near-field radius

            for _ in range(100):
                m._disease_step()
                if sus_agent.status == Status.INFECTED:
                    break  

            return sus_agent.n_dose

        dose_close = run_and_get_dose(close=True)
        dose_far   = run_and_get_dose(close=False)

        if dose_close is None or dose_far is None:
            pytest.skip("Could not set up near-field scenario")

        assert dose_close >= dose_far, \
            f"Close agent dose ({dose_close:.6f}) should be >= far agent dose ({dose_far:.6f})"

    def test_far_field_used_when_no_near_field_agent(self):
        
        m = HospitalModel(dict(BASE_PARAMS))
        living = m._living_agents()
        sus = next(
            (a for a in living
             if a.status == Status.SUSCEPTIBLE and isinstance(a, PatientAgent)),
            None
        )
        if sus is None:
            pytest.skip("Need a susceptible patient agent")

        room = m.floor_plan.room_by_name(sus.current_room_name)
        if room is None:
            pytest.skip("Susceptible patient has no room assigned")

        room.C_FF = 2.0
        sus.pos = (50.0, 50.0)

        for a in living:
            if a.status == Status.INFECTED:
                a.current_room_name = "nowhere"

        dose_before = sus.n_dose
        m._disease_step()
        di = sus.n_dose - dose_before

        expected = room.C_FF * sus.breathing_rate * (1.0 - sus.mask_efficiency) * m.p["delta_t"]
        assert di == pytest.approx(expected, rel=0.1), \
            f"Dose increment should equal C_FF*BR*dt={expected:.6f}, got {di:.6f}"

    def test_hepa_cleaner_reduces_cff(self):
       
        def run_steps(with_cleaner, steps=30):
            m = HospitalModel(dict(BASE_PARAMS))

            living = m._living_agents()
            inf = next(
                (a for a in living
                 if a.status == Status.INFECTED
                 and isinstance(a, PatientAgent)
                 and a.current_room_name),
                None
            )
            if inf is None:

                inf = next(
                    (a for a in living
                     if a.status == Status.INFECTED and a.current_room_name),
                    None
                )
            if inf is None:
                return None

            room = m.floor_plan.room_by_name(inf.current_room_name)
            if room is None:
                return None
            room.C_FF = 0.0

            if with_cleaner:
                cleaner = next(
                    (a for a in living if isinstance(a, CleanerAgent)), None
                )
                if cleaner:
                    cleaner.current_room_name = inf.current_room_name

            for _ in range(steps):
                m._disease_step()
            return room.C_FF

        c_without = run_steps(with_cleaner=False)
        c_with    = run_steps(with_cleaner=True)

        if c_without is None or c_with is None:
            pytest.skip("Could not find infected patient with valid room")

        assert c_with < c_without, \
            f"HEPA should reduce C_FF: without={c_without:.6f}, with={c_with:.6f}"

    def test_cleaner_targets_most_occupied_room(self):

        m = HospitalModel(dict(BASE_PARAMS))
        living = m._living_agents()
        cleaner = next(
            (a for a in living if isinstance(a, CleanerAgent)), None
        )
        if cleaner is None:
            pytest.skip("No cleaner agent in model")

        accessible = [
            r for r in m.floor_plan.rooms
            if "cleaner" in r.access and r.name != cleaner.current_room_name
        ]
        if len(accessible) < 2:
            pytest.skip("Need at least 2 cleaner-accessible rooms")

        crowded_room = accessible[0]
        empty_room   = accessible[1]

        agents_to_move = [a for a in living
                          if not isinstance(a, CleanerAgent)][:5]
        for a in agents_to_move:
            a.current_room_name = crowded_room.name

        target = cleaner._find_target()
        assert target == crowded_room.name, \
            f"Cleaner should target most occupied room '{crowded_room.name}', got '{target}'"

    def test_sir_state_transitions_are_one_way(self):
 
        params = dict(BASE_PARAMS)
        params["recovery_rate"] = 0.05 
        m = HospitalModel(params)
        state_history = {a.unique_id: [] for a in m._living_agents()}

        for _ in range(200):
            m.step()
            for a in m._living_agents():
                if a.unique_id in state_history:
                    state_history[a.unique_id].append(a.status)

        ORDER = {Status.SUSCEPTIBLE: 0, Status.INFECTED: 1, Status.RECOVERED: 2}
        for uid, history in state_history.items():
            for i in range(1, len(history)):
                prev = ORDER[history[i - 1]]
                curr = ORDER[history[i]]
                assert curr >= prev, \
                    f"Agent {uid} reversed state: {history[i-1]} → {history[i]} at step {i}"



# INTEGRATION TESTS


class TestModelInitialisation:
    def test_model_creates_correct_agent_counts(self, model):
        agents = model._living_agents()
        doctors   = sum(1 for a in agents if isinstance(a, DoctorAgent))
        nurses    = sum(1 for a in agents if isinstance(a, NurseAgent))
        cleaners  = sum(1 for a in agents if isinstance(a, CleanerAgent))
        patients  = sum(1 for a in agents if isinstance(a, PatientAgent))
        assert doctors  == BASE_PARAMS["num_doctors"]
        assert nurses   == BASE_PARAMS["num_nurses"]
        assert cleaners == BASE_PARAMS["num_cleaners"]
        assert patients == BASE_PARAMS["num_patients"]

    def test_initial_infected_count(self, model):
        infected = [a for a in model._living_agents() if a.status == Status.INFECTED]
        assert len(infected) == BASE_PARAMS["num_initially_infected"]

    def test_all_agents_have_positions(self, model):
        for a in model._living_agents():
            assert a.pos is not None, f"{a.agent_type} has no position after init"

    def test_datacollector_initialised(self, model):
        assert model.datacollector is not None


class TestSimulationRuns:

    def test_50_steps_no_exception(self):
        m = HospitalModel(dict(BASE_PARAMS))
        for _ in range(50):
            m.step()

    def test_sir_history_populated(self):
        m = HospitalModel(dict(BASE_PARAMS))
        for _ in range(10):
            m.step()
        assert len(m.sir_history) == 10

    def test_tick_count_increments(self):
        m = HospitalModel(dict(BASE_PARAMS))
        for _ in range(5):
            m.step()
        assert m.tick_count == 5


def _room_centroid(room):

    xs = [pt[0] for pt in room.polygon]
    ys = [pt[1] for pt in room.polygon]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


class TestPathfindingIntegration:


    def test_path_found_within_same_room(self, simple_fp):

        room = next(r for r in simple_fp.rooms if r.room_type != "corridor")
        cx, cy = _room_centroid(room)
        p1 = (cx - 10, cy)
        p2 = (cx + 10, cy)
        path = simple_fp.find_path(p1, p2)
        assert path is not None and len(path) > 0

    def test_path_respects_access_control(self, simple_fp):

        restricted = next(
            (r for r in simple_fp.rooms if "visitor" not in r.access), None
        )
        open_room = next(
            (r for r in simple_fp.rooms if "visitor" in r.access
             and r.room_type != "corridor"), None
        )
        if restricted is None or open_room is None:
            pytest.skip("Need both a restricted and an open room")
        start = _room_centroid(open_room)
        end   = _room_centroid(restricted)
        path  = simple_fp.find_path(start, end, agent_type="visitor")
        assert path is None or len(path) == 0, \
            "Visitor should not receive a path into a restricted room"

    def test_path_does_not_cross_walls(self, model):

        from floorplan import _wall_crosses
        fp = model.floor_plan
        accessible = [r for r in fp.rooms
                      if r.room_type in ("ward", "waiting", "corridor")]
        if len(accessible) < 2:
            pytest.skip("Need at least 2 accessible rooms")
        p1 = model.random_point_in_room(accessible[0].name)
        p2 = model.random_point_in_room(accessible[-1].name)
        if not p1 or not p2:
            pytest.skip("Could not get room points")
        path = fp.find_path(p1, p2)
        if not path:
            pytest.skip("No path found — rooms may not be connected")
        
        enforced_walls = fp.grid._walls
        for i in range(len(path) - 1):
            for wall in enforced_walls:
                assert not _wall_crosses(path[i], path[i + 1], wall), \
                    f"Path segment {path[i]}→{path[i+1]} crosses enforced wall {wall}"


class TestDiseaseTransmission:
 
    def test_infection_can_spread(self):

        params = dict(BASE_PARAMS)
        params.update({
            "num_patients": 8, "num_initially_infected": 1,
            "quanta_rate": 50.0, "recovery_rate": 0.0,  
            "random_seed": 1,
        })
        m = HospitalModel(params)
        for _ in range(300):
            m.step()
        total_ever_infected = len(m.transmission_events)
        assert total_ever_infected > 0, "No infections occurred in 300 steps"

    def test_c_ff_increases_with_infected_agent(self):

        m = HospitalModel(dict(BASE_PARAMS))

        infected = next(
            a for a in m._living_agents() if a.status == Status.INFECTED
        )
        room_name = infected.current_room_name
        room = m.floor_plan.room_by_name(room_name)
        if room is None:
            pytest.skip("Infected agent not in a named room yet")
        c_before = room.C_FF
        m._disease_step()
        assert room.C_FF >= c_before, "C_FF should not decrease when infected agent is present"

    def test_no_recovery_keeps_infected_count_stable(self):

        params = dict(BASE_PARAMS)
        params["recovery_rate"] = 0.0
        m = HospitalModel(params)
        prev_i = m._sir_i()
        for _ in range(50):
            m.step()
            assert m._sir_i() >= prev_i or m._sir_i() >= BASE_PARAMS["num_initially_infected"]


class TestGetResults:


    def test_get_results_keys(self):
        m = HospitalModel(dict(BASE_PARAMS))
        for _ in range(10):
            m.step()
        r = m.get_results()
        required = ["params", "floor_plan_name", "tick_count", "sir_history",
                    "new_infections_per_tick", "transmission_events",
                    "room_contamination", "estimated_total_pop"]
        for key in required:
            assert key in r, f"Missing key '{key}' in get_results()"



#VALIDATION TESTS


class TestWellsRileyValidation:


    def test_higher_ventilation_lower_contamination(self):
        
        def run_single_room(ach):
            r = Room("ward", "ward",
                     [[0,0],[200,0],[200,200],[0,200]],
                     ventilation_ach=ach, volume_m3=500.0)
            r.C_FF = 0.0
            q_base = 25.0; dt = 0.05; V = 500.0; Q = ach * V
            for _ in range(100):
                src = q_base / V
                decay = (Q / V) * r.C_FF
                r.C_FF = max(0.0, r.C_FF + (src - decay) * dt)
            return r.C_FF

        c_low  = run_single_room(ach=2)
        c_high = run_single_room(ach=20)
        assert c_low > c_high, \
            f"Low-ACH room ({c_low:.5f}) should have higher C_FF than high-ACH ({c_high:.5f})"

    def test_mask_reduces_attack_rate(self):
        
        def run(mask):
            params = dict(BASE_PARAMS)
            params.update({
                "mask_efficiency": mask,
                "num_patients": 10, "num_initially_infected": 2,
                "quanta_rate": 40.0, "recovery_rate": 0.0,
                "random_seed": 7,
                "patient_arrival_interval": 9999,
                "visitor_arrival_interval": 9999,
            })
            m = HospitalModel(params)
            for _ in range(200):
                m.step()
            return len(m.transmission_events)

        infections_no_mask   = run(0.0)
        infections_with_mask = run(0.9)
        assert infections_with_mask <= infections_no_mask, \
            f"Masks should reduce infections: no_mask={infections_no_mask}, masked={infections_with_mask}"

    def test_more_initial_infected_earlier_peak(self):
       
        def peak_tick(seed_count):
            params = dict(BASE_PARAMS)
            params.update({
                "num_initially_infected": seed_count,
                "num_patients": 12, "quanta_rate": 30.0,
                "recovery_rate": 0.002, "random_seed": 42,
            })
            m = HospitalModel(params)
            for _ in range(400):
                m.step()
            if not m.sir_history:
                return 400
            peak_i = max(s["I"] for s in m.sir_history)
            for s in m.sir_history:
                if s["I"] == peak_i:
                    return s["tick"]
            return 400

        tick_1 = peak_tick(1)
        tick_5 = peak_tick(5)
        assert tick_5 <= tick_1, \
            f"Larger seed should peak earlier: seed=1 peaks at {tick_1}, seed=5 at {tick_5}"


class TestSIRModelValidation:

    def test_sir_curve_monotone_recovered(self):
        
        m = HospitalModel(dict(BASE_PARAMS))
        prev_r = 0
        for _ in range(100):
            m.step()
            current_r = m._sir_r()
            assert current_r >= prev_r, \
                f"Recovered decreased: {prev_r} → {current_r} at tick {m.tick_count}"
            prev_r = current_r

    def test_sir_population_conserved_throughout(self):
        
        m = HospitalModel(dict(BASE_PARAMS))
        pop = m.estimated_total_pop
        for _ in range(50):
            m.step()
            total = m._sir_s() + m._sir_i() + m._sir_r()
            assert total == pop, \
                f"Population not conserved at tick {m.tick_count}: S+I+R={total}, expected={pop}"


class TestStochasticRobustness:
    
    def test_attack_rate_variance_across_seeds(self):
        
        import statistics
        params = dict(BASE_PARAMS)
        params.update({
            "num_patients": 10, "num_initially_infected": 2,
            "quanta_rate": 30.0, "recovery_rate": 0.003,
            "patient_arrival_interval": 9999,
            "visitor_arrival_interval": 9999,
        })
        attack_rates = []
        for seed in range(1, 6):
            params["random_seed"] = seed
            m = HospitalModel(dict(params))
            for _ in range(300):
                m.step()
            pop = m.estimated_total_pop
            infected = len(m.transmission_events) + params["num_initially_infected"]
            ar = (infected / pop * 100) if pop else 0
            attack_rates.append(ar)

        if len(attack_rates) > 1:
            std = statistics.stdev(attack_rates)
            mean = statistics.mean(attack_rates)
            print(f"\nAttack rates across 5 seeds: {[round(x,1) for x in attack_rates]}")
            print(f"Mean={mean:.1f}%  Std={std:.1f}%")
            assert std < 25.0, \
                f"High variance across seeds (std={std:.1f}%) suggests unstable model"

class TestBoundaryConditions:
    
    def test_zero_initial_infected(self):
        
        params = dict(BASE_PARAMS)
        params["num_initially_infected"] = 0
        m = HospitalModel(params)
        for _ in range(100):
            m.step()
        assert len(m.transmission_events) == 0, \
            "No transmissions should occur with zero initial infected"

    def test_all_agents_initially_infected(self):
        
        params = dict(BASE_PARAMS)
        params["num_initially_infected"] = params["num_patients"]
        params["recovery_rate"] = 0.05
        m = HospitalModel(params)
        for _ in range(100):
            m.step()
        assert m._sir_r() > 0, \
            "Some agents must have recovered when all start infected"

    def test_extremely_high_quanta_rate(self):
       
        params = dict(BASE_PARAMS)
        params.update({
            "quanta_rate": 25000.0,
            "recovery_rate": 0.0,
            "num_initially_infected": 1,
        })
        m = HospitalModel(params)
        for _ in range(50):
            m.step()
            s, i, r = m._sir_s(), m._sir_i(), m._sir_r()
            assert s >= 0, f"S went negative at tick {m.tick_count}: S={s}"
            assert not math.isnan(s + i + r), \
                f"NaN in SIR counts at tick {m.tick_count}"
            assert s + i + r == m.estimated_total_pop, \
                "Population not conserved under extreme quanta rate"

    def test_zero_ventilation(self):
        
        params = dict(BASE_PARAMS)
        params["num_initially_infected"] = 2
        m = HospitalModel(params)

        
        for room in m.floor_plan.rooms:
            room.ventilation_ach = 0.0
            room.q_ventilation = 0.0

        try:
            for _ in range(50):
                m._disease_step()
        except ZeroDivisionError:
            pytest.fail("Model crashed with ZeroDivisionError at zero ventilation")
        except Exception as e:
            pytest.fail(f"Model crashed with unexpected error at zero ventilation: {e}")

        
        contaminated = [r for r in m.floor_plan.rooms if r.C_FF > 0]
        assert len(contaminated) > 0, \
            "C_FF should accumulate with zero ventilation"

    def test_single_agent_simulation(self):
        
        params = dict(BASE_PARAMS)
        params.update({
            "num_doctors": 0, "num_nurses": 0,
            "num_cleaners": 0, "num_volunteers": 0,
            "num_patients": 1, "num_initially_infected": 0,
            "patient_arrival_interval": 9999,
            "visitor_arrival_interval": 9999,
        })
        try:
            m = HospitalModel(params)
            for _ in range(50):
                m.step()
        except Exception as e:
            pytest.fail(f"Model crashed with single agent: {e}")

        assert len(m.transmission_events) == 0

    def test_mask_efficiency_at_maximum(self):
        
        params = dict(BASE_PARAMS)
        params.update({
            "mask_efficiency": 1.0,
            "num_initially_infected": 3,
            "quanta_rate": 100.0,
            "recovery_rate": 0.0,
        })
        m = HospitalModel(params)
        for _ in range(200):
            m.step()

        assert len(m.transmission_events) == 0, \
            "Perfect masks (efficiency=1.0) should produce zero new infections"