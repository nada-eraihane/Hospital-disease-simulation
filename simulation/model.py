from __future__ import annotations
import random, math, time
from typing import List, Optional, Dict
from mesa import Model
from mesa.space import ContinuousSpace
from mesa.datacollection import DataCollector
from floorplan import FloorPlan, load_predefined, dist, point_in_polygon
from agents import (HospitalAgent, PatientAgent, DoctorAgent, NurseAgent, VisitorAgent, CleanerAgent, VolunteerAgent, Status, NEAR_FIELD_RADIUS, _dist, ADMITTING_ROOM_TYPES, STAFFED_ROOM_TYPES)


class HospitalModel(Model):
    def __init__(self, params: dict, floor_plan: Optional[FloorPlan] = None):
        super().__init__()
        self.p = {
            "num_doctors":2,
            "num_nurses":4,
            "num_cleaners":2,
            "num_volunteers":2,
            "num_patients":12,
            "num_initially_infected":2,
            "patient_arrival_interval":15,
            "infected_arrival_fraction":0.1,
            "visiting_hours_start":100,
            "visiting_hours_end":300,
            "visitor_arrival_interval":20,
            "quanta_rate":25.0,
            "near_field_radius":1.5,
            "random_air_speed":5.0,
            "recovery_rate":0.003,
            "mask_efficiency":0.0,
            "hepa_cadr":300.0,
            "delta_t":0.05,
            "sim_speed":10,
            "max_steps":1000,
            "random_seed":42,
            "floor_plan_name":"medium",
        }
        self.p.update(params)
        random.seed(self.p["random_seed"])
        self.floor_plan = floor_plan if floor_plan else load_predefined(self.p["floor_plan_name"])
        self.space = ContinuousSpace(x_max=self.floor_plan.width, y_max=self.floor_plan.height, torus=False)

        self.tick_count = 0
        self.running = True
        self.transmission_events: List[dict] = []
        self.sir_history: List[dict] = []
        self.new_infections_per_tick: List[int] = []
        self._removed_agents: set = set()
        self.infection_log: List[str] = []
        self._departed_status: List[str] = []
        #cumulative contamination for analytics heatmap
        self.room_contamination_history: Dict[str, float] = {r.name: 0.0 for r in self.floor_plan.rooms}

        #NFconstants
        r = self.p["near_field_radius"]
        self.V_NF = (2.0/3.0) * math.pi * (r ** 3)
        self.beta_interzonal = 0.5 * (self.p["random_air_speed"] * 60.0) * (2.0 * math.pi * (r ** 2))

        #office tracking
        self._office_occupant: Dict[str, Optional[int]] = {}
        for room in self.floor_plan.rooms:
            if room.room_type == "office": self._office_occupant[room.name] = None

        self._admitting_rooms = [r for r in self.floor_plan.rooms
            if r.room_type in ADMITTING_ROOM_TYPES and self.floor_plan.beds_in_room(r.name)]
        self._staffable_rooms = [r for r in self.floor_plan.rooms if r.room_type in STAFFED_ROOM_TYPES]

        #estimated total population for SIR graph
        max_ticks = self.p["max_steps"]
        arr_interval = max(1, self.p["patient_arrival_interval"])
        vis_interval = max(1, self.p["visitor_arrival_interval"])
        vis_window = max(0, self.p["visiting_hours_end"] - self.p["visiting_hours_start"])
        initial_staff = self.p["num_doctors"] + self.p["num_nurses"] + self.p["num_cleaners"] + self.p["num_volunteers"]
        initial_patients = self.p["num_patients"]
        est_arriving_patients = int(max_ticks / arr_interval)
        est_visitors = int(vis_window / vis_interval)
        self.estimated_total_pop = initial_staff + initial_patients + est_arriving_patients + est_visitors
        self._total_agents_created = 0

        #create agents
        self._create_patients()
        self._create_staff()
        self._total_agents_created = len(self._living_agents())
        self._assign_initially_infected()

        self.datacollector = DataCollector(model_reporters={
            "Susceptible": lambda m: m._sir_s(), "Infected": lambda m: m._sir_i(),
            "Recovered": lambda m: m._sir_r(), "Tick": lambda m: m.tick_count})

    def _living_agents(self): return [a for a in self.agents if isinstance(a,HospitalAgent) and not a.removed and a.pos is not None]
    def room_occupancy(self, n): return sum(1 for a in self._living_agents() if a.current_room_name==n)
    def is_room_full(self, n):
        r=self.floor_plan.room_by_name(n); return r is not None and self.room_occupancy(n)>=r.capacity

    def random_point_in_room(self, name):
        r=self.floor_plan.room_by_name(name)
        if r is None: return None
        poly=r.polygon; xs=[p[0] for p in poly]
        ys=[p[1] for p in poly]
        for _ in range(30):
            x=random.uniform(min(xs)+5,max(xs)-5) 
            y=random.uniform(min(ys)+5,max(ys)-5)
            if point_in_polygon((x,y),poly): return (x,y)
        return r.centroid

    def assign_bed_for_patient(self):
        rooms_with_space = []
        for room in self._admitting_rooms:
            beds = self.floor_plan.beds_in_room(room.name)
            occ = sum(1 for b in beds if b.assigned_patient is not None)
            free = len(beds) - occ
            if free > 0: rooms_with_space.append((room, occ, free))
        if not rooms_with_space: return None
        rooms_with_space.sort(key=lambda x: x[1])
        free_beds = [b for b in self.floor_plan.beds_in_room(rooms_with_space[0][0].name) if b.assigned_patient is None]
        return random.choice(free_beds) if free_beds else None

    def request_office(self, p):
        for n in self._office_occupant:
            if self._office_occupant[n] is None: self._office_occupant[n]=p.unique_id; return n
        return None
    def release_office(self, n):
        if n in self._office_occupant: self._office_occupant[n]=None

    #SIR counting
    def _sir_s(self):
        live = sum(1 for a in self._living_agents() if a.status == Status.SUSCEPTIBLE)
        dep = sum(1 for s in self._departed_status if s == Status.SUSCEPTIBLE)
        
        not_arrived = max(0, self.estimated_total_pop - self._total_agents_created)
        return live + dep + not_arrived
    
    def _sir_i(self):
        return sum(1 for a in self._living_agents() if a.status == Status.INFECTED) + sum(1 for s in self._departed_status if s == Status.INFECTED)
    
    def _sir_r(self):
        return sum(1 for a in self._living_agents() if a.status == Status.RECOVERED) + sum(1 for s in self._departed_status if s == Status.RECOVERED)

    def _place_at_entrance(self, agent):
        ents=self.floor_plan.entrances
        if ents:
            x,y=ents[0].position
            self.space.place_agent(agent,(x+random.uniform(-15,15),y+random.uniform(-15,15)))
        else:
            self.space.place_agent(agent,(50,self.floor_plan.height/2))
    
    def _place_in_room(self, agent, name):
        pos = self.random_point_in_room(name)
        if pos: 
            self.space.place_agent(agent,pos)
        else: 
            self._place_at_entrance(agent)

    def _create_patients(self):
        for i in range(self.p["num_patients"]):
            bed = self.assign_bed_for_patient()
            if bed is None: 
                break
            p = PatientAgent(self,is_outpatient=False,stagger=i*37)
            p.assigned_bed = bed
            bed.assigned_patient = p.unique_id
            self.space.place_agent(p,bed.position)
            p.state  = PatientAgent.AT_BED
            p.current_room_name = bed.room_name
            p.mask_efficiency = self.p["mask_efficiency"]

    def _create_staff(self):
        fp = self.floor_plan
        staffable = list(self._staffable_rooms) if self._staffable_rooms else [r for r in fp.rooms if r.room_type!="corridor"]
        nurse_rooms = [r for r in self._admitting_rooms] if self._admitting_rooms else staffable
        for i in range(self.p["num_doctors"]):
            rm = staffable[ i % len(staffable)]
            d = DoctorAgent(self, assigned_room_name = rm.name)
            d.mask_efficiency=self.p["mask_efficiency"]
            self._place_in_room(d,rm.name) 
            d._load_beds()
            if d.bed_list: 
                d.set_path_to(d.bed_list[0].position)
        for i in range(self.p["num_nurses"]):
            rm = nurse_rooms[i %  len(nurse_rooms)]
            n = NurseAgent(self,assigned_room_name=rm.name); 
            n.mask_efficiency = self.p["mask_efficiency"]
            self._place_in_room(n,rm.name); 
            n._load_beds()
            if n.bed_list: 
                n.set_path_to(n.bed_list[0].position)
        for _ in range(self.p["num_cleaners"]):
            c = CleanerAgent(self)
            c.mask_efficiency = self.p["mask_efficiency"] 
            self._place_at_entrance(c)
        for _ in range(self.p["num_volunteers"]):
            v=  VolunteerAgent(self)
            v.mask_efficiency = self.p["mask_efficiency"]; 
            self._place_at_entrance(v)
            rooms = fp.accessible_rooms("volunteer")
            if rooms: 
                v.set_path_to_room(random.choice(rooms).name)

    def _assign_initially_infected(self):
        living=self._living_agents()
        n=min(self.p["num_initially_infected"],len(living))
        for a in random.sample(living,n):
            a.status=Status.INFECTED
            self.infection_log.append(f"Tick 0: {a.agent_type.title()} started infected in {a.current_room_name}")

    def _spawn_patient(self):
        lam=self.p["patient_arrival_interval"]
        if lam <= 0 or random.random() >= (1.0 / lam):
            return
        is_out = random.random()<0.10
        p = PatientAgent(self,is_outpatient = is_out,stagger = random.randint(0,200))
        p.mask_efficiency =   self.p["mask_efficiency"]
        if random.random()<self.p["infected_arrival_fraction"]:
            p.status=Status.INFECTED
        self._place_at_entrance(p)
        self._total_agents_created+=1
        if not is_out:
            bed = self.assign_bed_for_patient()
            if bed: 
                p.assigned_bed = bed 
                bed.assigned_patient= p.unique_id
        waiting = [r for r in self.floor_plan.rooms if r.room_type=="waiting" and "patient" in r.access]
        if waiting: 
            p.set_path_to_room(waiting[0].name)

    def _spawn_visitor(self):
        t=self.tick_count
        if t<self.p["visiting_hours_start"] or t>self.p["visiting_hours_end"]: 
            return
        lam=self.p["visitor_arrival_interval"]
        if lam<=0 or random.random()>=(1.0/lam): 
            return
        admitted=[a for a in self._living_agents() if isinstance(a,PatientAgent) and a.state==PatientAgent.AT_BED and a.assigned_bed]
        if not admitted: 
            return
        tgt=  random.choice(admitted)
        v = VisitorAgent(self,target_bed=tgt.assigned_bed); 
        v.mask_efficiency = self.p["mask_efficiency"]
        self._place_at_entrance(v) 
        self._total_agents_created+=1
        v.set_path_to(tgt.assigned_bed.position)

    def remove_agent(self, agent):
        agent.removed=True 
        self._removed_agents.add(agent.unique_id)
        self._departed_status.append(agent.status)
        if isinstance(agent,PatientAgent) and agent.assigned_bed: 
            agent.assigned_bed.assigned_patient=None
        for n in self._office_occupant:
            if self._office_occupant[n]==agent.unique_id: self._office_occupant[n]=None
        try: 
            self.space.remove_agent(agent)
        except: 
            pass

    def _disease_step(self):
        living=self._living_agents()
        dt=self.p["delta_t"]
        q_base=self.p["quanta_rate"]
        mask=self.p["mask_efficiency"]
        hepa=self.p["hepa_cadr"]
        new_inf=0

        for room in self.floor_plan.rooms:
            here = [a for a in living if a.current_room_name  ==room.name]
            inf_here = [a for a in here if a.status==Status.INFECTED]
            V = max(room.volume_m3,1.0) 
            Q = room.q_ventilation
            Q_eff = Q + hepa if any(isinstance(a,CleanerAgent) for a in here) else Q
            q_eff = q_base *(1.0-mask)
            src =(len(inf_here)*q_eff)/V
            decay =(Q_eff/V)*room.C_FF
            room.C_FF =max(0.0,room.C_FF+(src-decay)*dt)
            self.room_contamination_history[room.name] += room.C_FF * dt  
            for inf in inf_here:
                iq=q_base*(1.0-inf.mask_efficiency)
                ns=iq/self.V_NF
                ne=(self.beta_interzonal/self.V_NF)*(inf.C_NF-room.C_FF)
                inf.C_NF=max(0.0,inf.C_NF+(ns-ne)*dt)

        for sus in [a for a in living if a.status ==Status.SUSCEPTIBLE]:
            if not sus.current_room_name: continue
            room=self.floor_plan.room_by_name(sus.current_room_name)
            if room is None: 
                continue
            C=room.C_FF
            same_room_inf=[a for a in living if a.status==Status.INFECTED and a.current_room_name==sus.current_room_name and a.pos]
            if sus.pos and same_room_inf:
                for ia in same_room_inf:
                    if _dist(sus.pos,ia.pos)<=NEAR_FIELD_RADIUS: C=max(C,ia.C_NF)
            pe = sus.breathing_rate * (1.0 - sus.mask_efficiency )
            di = C * pe * dt
            sus.n_dose += di
            if random.random() < (1.0 - math.exp(-di)):
                sus.status = Status.INFECTED
                sus.C_NF = 0.0; new_inf += 1
                self.infection_log.append(f"Tick {self.tick_count}: {sus.agent_type.title()} infected in {sus.current_room_name}")
                self.transmission_events.append({
                    "tick":self.tick_count,
                    "agent_id":sus.unique_id,
                    "agent_type":sus.agent_type,
                    "room":sus.current_room_name,
                    "dose":sus.n_dose})

        for a in [a for a in living if a.status==Status.INFECTED]:
            if random.random()<self.p["recovery_rate"]: a.status=Status.RECOVERED; a.C_NF=0.0
        self.new_infections_per_tick.append(new_inf)

    def step(self):
        self.tick_count += 1
        self._spawn_patient() 
        self._spawn_visitor()
        living = self._living_agents()
        random.shuffle(living)
        for a in living: a.step()
        self._disease_step()
        s = self._sir_s() 
        i=self._sir_i() 
        r = self._sir_r()
        current=len(self._living_agents())
        self.sir_history.append({"tick":self.tick_count,"S":s,"I":i,"R":r,
            "current_agents":current,"total_agents":self._total_agents_created})
        self.datacollector.collect(self)
        if self.tick_count>=self.p["max_steps"]: self.running=False

    def get_results(self):
        living = self._living_agents()
        return {
            "params":self.p, "floor_plan_name":self.floor_plan.name,
            "tick_count":self.tick_count, "sir_history":self.sir_history,
            "new_infections_per_tick":self.new_infections_per_tick,
            "transmission_events":self.transmission_events,
            "infection_log":self.infection_log,
            "estimated_total_pop":self.estimated_total_pop,
            "total_created":self._total_agents_created,
            "departed_status":self._departed_status,
            "room_contamination":self.room_contamination_history,
            "agent_summary":[{"id":a.unique_id,"type":a.agent_type,
                              "status":a.status,"dose":a.n_dose,
                              "room":a.current_room_name} for a in living],
            "timestamp":time.strftime("%Y-%m-%d %H:%M:%S"),
        }
