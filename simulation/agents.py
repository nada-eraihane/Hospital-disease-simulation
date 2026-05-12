from __future__ import annotations
import math, random
from typing import List, Optional, Tuple, TYPE_CHECKING
from mesa import Agent

if TYPE_CHECKING:
    from model import HospitalModel

class Status:
    SUSCEPTIBLE = "S"
    INFECTED = "I"
    RECOVERED = "R"

AGENT_SPEEDS = {"patient":4.0,"doctor":7.0,"nurse":6.0,"visitor":5.0,"cleaner":5.0,"volunteer":5.0}
BREATHING_RATES = {"patient":0.3,"doctor":0.7,"nurse":0.7,"visitor":0.4,"cleaner":0.8,"volunteer":0.5}
AGENT_SHAPES = {"patient":"circle","doctor":"diamond","nurse":"square","visitor":"triangle_up","cleaner":"triangle_down","volunteer":"hexagon"}
STATUS_COLOURS = {Status.SUSCEPTIBLE:"#22C55E",Status.INFECTED:"#EF4444",Status.RECOVERED:"#9CA3AF"}
NEAR_FIELD_RADIUS = 1.5
ADMITTING_ROOM_TYPES = {"ward","icu"}
STAFFED_ROOM_TYPES = {"ward","icu","special"}
ENTRANCE_STUCK_TIMEOUT = 30  # ticks near entrance before force-removal (~3s at default speed)

def _dist(a,b): return math.hypot(a[0]-b[0],a[1]-b[1])


class HospitalAgent(Agent):
    ARRIVE_RADIUS = 8.0
    ARRIVE_RADIUS_BED = 10.0
    ARRIVE_RADIUS_EXIT = 25.0
    SEPARATION_RADIUS = 12.0
    SEPARATION_STRENGTH = 2.0

    def __init__(self, model, agent_type):
        super().__init__(model)
        self.agent_type = agent_type
        self.status = Status.SUSCEPTIBLE
        self.removed = False
        self.max_speed = AGENT_SPEEDS.get(agent_type,5.0)*(0.9+random.random()*0.2)
        self.current_path: List[Tuple[float,float]] = []
        self.path_index = 0
        self.target_pos = None
        self.dwell_remaining = 0
        self.n_dose = 0.0
        self.breathing_rate = BREATHING_RATES.get(agent_type,0.5)
        self.C_NF = 0.0
        self.mask_efficiency = 0.0
        self.current_room_name = ""
        self._path_was_set = False
        self.entrance_stuck_ticks = 0

    def set_path_to(self, pos):
        if self.pos is None: return False
        path = self.model.floor_plan.find_path(self.pos, pos, self.agent_type)
        if not path:
            return False
        self.current_path = path
        self.path_index = 0 
        self.target_pos = path[0]
        self._path_was_set = True
        return True

    def set_path_to_room(self, room_name):
        room = self.model.floor_plan.room_by_name(room_name)
        if room is None or self.agent_type not in room.access: return False
        if self.model.is_room_full(room_name): return False
        t = self.model.random_point_in_room(room_name)
        return self.set_path_to(t) if t else False

    def set_path_to_room_type(self, room_type):
        rooms = [r for r in self.model.floor_plan.rooms
                 if r.room_type==room_type and self.agent_type in r.access
                 and not self.model.is_room_full(r.name)]
        if not rooms: return False
        rooms.sort(key=lambda r: self.model.room_occupancy(r.name))
        return self.set_path_to_room(rooms[0].name)

    def _move(self):

        if self.pos is None or self.target_pos is None: return
        dx=self.target_pos[0]-self.pos[0]; dy=self.target_pos[1]-self.pos[1]
        d=math.hypot(dx,dy)
        is_final = self.path_index >= len(self.current_path)-1
        if is_final and self._is_entrance_target():
            ar = self.ARRIVE_RADIUS_EXIT
        elif is_final and self._is_bed_target():
            ar = self.ARRIVE_RADIUS_BED
        else:
            ar = self.ARRIVE_RADIUS
        if d<=max(ar, self.max_speed):
            if not is_final: self.model.space.move_agent(self, self.target_pos)
            self.path_index+=1
            if self.path_index>=len(self.current_path):
                self.target_pos=None; self.current_path=[]; self.path_index=0
            else: self.target_pos=self.current_path[self.path_index]
        else:
            nx=self.pos[0]+(dx/d)*self.max_speed; ny=self.pos[1]+(dy/d)*self.max_speed
            nx,ny=self._separate(nx,ny)
            nx=max(2,min(self.model.floor_plan.width-2,nx))
            ny=max(2,min(self.model.floor_plan.height-2,ny))
            self.model.space.move_agent(self,(nx,ny))

    def _separate(self,nx,ny):
        
        nbs=self.model.space.get_neighbors((nx,ny),radius=self.SEPARATION_RADIUS,include_center=False)
        px=py=0.0
        for o in nbs:
            if o.pos is None or getattr(o,'removed',False): continue
            d=_dist((nx,ny),o.pos)
            if 0<d<self.SEPARATION_RADIUS:
                s=(self.SEPARATION_RADIUS-d)/self.SEPARATION_RADIUS
                px+=((nx-o.pos[0])/d)*s*self.SEPARATION_STRENGTH
                py+=((ny-o.pos[1])/d)*s*self.SEPARATION_STRENGTH
        return nx+px,ny+py

    def _is_bed_target(self):
        if not self.current_path: return False
        f=self.current_path[-1]
        return any(_dist(f,b.position)<5 for b in self.model.floor_plan.beds)

    def _is_entrance_target(self):
        if not self.current_path: return False
        f=self.current_path[-1]
        return any(_dist(f,e.position)<15 for e in self.model.floor_plan.entrances)

    def is_moving(self): return self.target_pos is not None
    def has_arrived(self): 
        return self._path_was_set and self.target_pos is None and not self.current_path
    def _update_room(self):
        if self.pos:
            r=self.model.floor_plan.room_at(self.pos)
            self.current_room_name=r.name if r else ""
    def _role_behaviour(self): pass

    def step(self):
        if self.removed or self.pos is None:
            return
        self._update_room()
        self._role_behaviour()
        if self.dwell_remaining>0: 
            self.dwell_remaining-=1
        else: 
            self._move()


#patient
class PatientAgent(HospitalAgent):
    AT_WAITING="at_waiting"; AT_BED="at_bed"; AT_OFFICE="at_office"
    AT_WASHROOM="at_washroom"; TRAVELLING="travelling"
    WAITING_FOR_OFFICE="waiting_for_office"; DISCHARGING="discharging"

    def __init__(self, model, is_outpatient=False, stagger=0):
        super().__init__(model,"patient")
        self.is_outpatient=is_outpatient
        self.state=self.TRAVELLING; self.next_state=self.AT_WAITING
        self.assigned_bed=None
        self.waiting_duration=random.randint(5,15)
        self.office_duration=random.randint(10,20)
        self.max_stay=random.randint(500,700)  
        self.stay_ticks=0
        self.max_washroom_trips=random.randint(1,2)
        self.washroom_trips=0
        self.washroom_timer=random.randint(200,400)+stagger
        self.wait_ticks=0; self.max_wait=random.randint(30,60)

    def _role_behaviour(self):
        if self.state==self.TRAVELLING:
            if self.has_arrived():
                self.state=self.next_state
                if self.state==self.AT_WAITING: self.dwell_remaining=self.waiting_duration
                elif self.state==self.AT_OFFICE: self.dwell_remaining=self.office_duration
                elif self.state==self.AT_WASHROOM: self.dwell_remaining=random.randint(5,10)
                elif self.state==self.AT_BED: self.stay_ticks=0
            return
        if self.state==self.AT_WAITING:
            if self.dwell_remaining<=0:
                if self.is_outpatient:
                    off=self.model.request_office(self)
                    if off: self._go(off,self.AT_OFFICE)
                    else: self.state=self.WAITING_FOR_OFFICE
                elif self.assigned_bed:
                    self.set_path_to(self.assigned_bed.position)
                    self.state=self.TRAVELLING; self.next_state=self.AT_BED
                else: self._discharge()
            return
        if self.state==self.WAITING_FOR_OFFICE:
            self.wait_ticks+=1
            if self.wait_ticks>self.max_wait: self._discharge(); return
            off=self.model.request_office(self)
            if off: self._go(off,self.AT_OFFICE)
            return
        if self.state==self.AT_OFFICE:
            if self.dwell_remaining<=0:
                self.model.release_office(self.current_room_name); self._discharge()
            return
        if self.state == self.AT_BED:
            self.stay_ticks += 1
            if self.status == Status.RECOVERED or self.stay_ticks >= self.max_stay:
                self._discharge()
                return
            if self.washroom_trips < self.max_washroom_trips:
                self.washroom_timer -= 1
                if self.washroom_timer <= 0:
                    self.washroom_trips += 1
                    if self.set_path_to_room_type("washroom"):
                        self.state=self.TRAVELLING
                        self.next_state=self.AT_WASHROOM
                    else: 
                        self.washroom_timer=random.randint(150,300)
            return
        if self.state==self.AT_WASHROOM:
            if self.dwell_remaining<=0 and self.assigned_bed:
                self.set_path_to(self.assigned_bed.position)
                self.state=self.TRAVELLING; self.next_state=self.AT_BED
            return
        if self.state==self.DISCHARGING:
            if self.has_arrived():
                self.model.remove_agent(self)
                return
            ents=self.model.floor_plan.entrances
            if ents and self.pos and _dist(self.pos,ents[0].position)<=self.ARRIVE_RADIUS_EXIT:
                self.entrance_stuck_ticks+=1
                if self.entrance_stuck_ticks>=ENTRANCE_STUCK_TIMEOUT:
                    self.model.remove_agent(self)
            return

    def _go(self,room,state):
        self.state=self.TRAVELLING; self.next_state=state; self.set_path_to_room(room)
    def _discharge(self):
        self.state=self.DISCHARGING
        self.entrance_stuck_ticks=0
        ents=self.model.floor_plan.entrances
        if ents: self.set_path_to(ents[0].position)
        else: self.model.remove_agent(self)

#doctor
class DoctorAgent(HospitalAgent):
    VISITING_BED="visiting_bed"; TRAVELLING="travelling"
    ON_BREAK="on_break"; AT_WASHROOM="at_washroom"; IDLE="idle"

    def __init__(self, model, assigned_room_name=""):
        super().__init__(model,"doctor")
        self.assigned_room_name=assigned_room_name
        self.bed_list=[]; self.bed_index=0
        self.state=self.TRAVELLING; self.next_state=self.VISITING_BED

    def _load_beds(self):
        if not self.assigned_room_name: self.bed_list=[]; return
        beds=self.model.floor_plan.beds_in_room(self.assigned_room_name)
        self.bed_list=[b for b in beds if b.assigned_patient is not None]
        self.bed_index=0

    def _advance(self):
        self.bed_index+=1
        while self.bed_index<len(self.bed_list):
            if self.bed_list[self.bed_index].assigned_patient is not None: break
            self.bed_index+=1
        if self.bed_index<len(self.bed_list):
            self.state=self.TRAVELLING; self.next_state=self.VISITING_BED
            self.set_path_to(self.bed_list[self.bed_index].position)
        else: self._go_break()

    def _role_behaviour(self):
        if self.state==self.TRAVELLING:
            if self.has_arrived():
                self.state=self.next_state
                if self.state==self.VISITING_BED:
                    if self.bed_index<len(self.bed_list) and self.bed_list[self.bed_index].assigned_patient is not None:
                        self.dwell_remaining=random.randint(15,25)  
                    else: self._advance()
                elif self.state==self.ON_BREAK: self.dwell_remaining=random.randint(20,30)
                elif self.state==self.AT_WASHROOM: self.dwell_remaining=random.randint(5,10)
                elif self.state==self.IDLE: self.dwell_remaining=random.randint(30,50)
            return
        if self.state==self.IDLE:
            if self.dwell_remaining<=0:
                self._load_beds()
                if self.bed_list:
                    self.state=self.TRAVELLING; self.next_state=self.VISITING_BED
                    self.set_path_to(self.bed_list[0].position)
                else: self.dwell_remaining=random.randint(30,50)
            return
        if self.state==self.VISITING_BED:
            if self.dwell_remaining<=0: self._advance()
            return
        if self.state==self.ON_BREAK:
            if self.dwell_remaining<=0:
                if self.set_path_to_room_type("washroom"):
                    self.state=self.TRAVELLING; self.next_state=self.AT_WASHROOM
                else: self._return()
            return
        if self.state==self.AT_WASHROOM:
            if self.dwell_remaining<=0: self._return()
            return

    def _go_break(self):
        if self.set_path_to_room_type("staff_room"):
            self.state=self.TRAVELLING; self.next_state=self.ON_BREAK
        else: self._return()
    def _return(self):
        self._load_beds()
        if self.bed_list:
            self.state=self.TRAVELLING; self.next_state=self.VISITING_BED
            self.set_path_to(self.bed_list[0].position)
        elif self.assigned_room_name:
            self.state=self.TRAVELLING; self.next_state=self.IDLE
            self.set_path_to_room(self.assigned_room_name)

#nurse
class NurseAgent(HospitalAgent):
    VISITING_BED="visiting_bed"; TRAVELLING="travelling"
    ON_BREAK="on_break"; AT_WASHROOM="at_washroom"; IDLE="idle"

    def __init__(self, model, assigned_room_name=""):
        super().__init__(model,"nurse")
        self.assigned_room_name=assigned_room_name
        self.bed_list=[]; self.bed_index=0
        self.state=self.TRAVELLING; self.next_state=self.VISITING_BED

    def _load_beds(self):
        if not self.assigned_room_name: self.bed_list=[]; return
        beds=self.model.floor_plan.beds_in_room(self.assigned_room_name)
        self.bed_list=[b for b in beds if b.assigned_patient is not None]
        self.bed_index=0

    def _advance(self):
        self.bed_index+=1
        while self.bed_index<len(self.bed_list):
            if self.bed_list[self.bed_index].assigned_patient is not None: break
            self.bed_index+=1
        if self.bed_index<len(self.bed_list):
            self.state=self.TRAVELLING; self.next_state=self.VISITING_BED
            self.set_path_to(self.bed_list[self.bed_index].position)
        else: self._go_break()

    def _role_behaviour(self):
        if self.state==self.TRAVELLING:
            if self.has_arrived():
                self.state=self.next_state
                if self.state==self.VISITING_BED:
                    if self.bed_index<len(self.bed_list) and self.bed_list[self.bed_index].assigned_patient is not None:
                        self.dwell_remaining=random.randint(8,15) 
                    else: self._advance()
                elif self.state==self.ON_BREAK: self.dwell_remaining=random.randint(20,30)
                elif self.state==self.AT_WASHROOM: self.dwell_remaining=random.randint(5,10)
                elif self.state==self.IDLE: self.dwell_remaining=random.randint(30,50)
            return
        if self.state==self.IDLE:
            if self.dwell_remaining<=0:
                self._load_beds()
                if self.bed_list:
                    self.state=self.TRAVELLING; self.next_state=self.VISITING_BED
                    self.set_path_to(self.bed_list[0].position)
                else: self.dwell_remaining=random.randint(30,50)
            return
        if self.state==self.VISITING_BED:
            if self.dwell_remaining<=0: self._advance()
            return
        if self.state==self.ON_BREAK:
            if self.dwell_remaining<=0:
                if self.set_path_to_room_type("washroom"):
                    self.state=self.TRAVELLING; self.next_state=self.AT_WASHROOM
                else: self._return()
            return
        if self.state==self.AT_WASHROOM:
            if self.dwell_remaining<=0: self._return()
            return

    def _go_break(self):
        if self.set_path_to_room_type("staff_room"):
            self.state=self.TRAVELLING; self.next_state=self.ON_BREAK
        else: self._return()
    def _return(self):
        self._load_beds()
        if self.bed_list:
            self.state=self.TRAVELLING; self.next_state=self.VISITING_BED
            self.set_path_to(self.bed_list[0].position)
        elif self.assigned_room_name:
            self.state=self.TRAVELLING; self.next_state=self.IDLE
            self.set_path_to_room(self.assigned_room_name)

#visitors
class VisitorAgent(HospitalAgent):
    TRAVELLING="travelling"; AT_BEDSIDE="at_bedside"
    AT_WASHROOM="at_washroom"; LEAVING="leaving"

    def __init__(self, model, target_bed=None):
        super().__init__(model,"visitor")
        self.target_bed =target_bed
        self.state=self.TRAVELLING; self.next_state=self.AT_BEDSIDE
        self.bedside_duration=random.randint(40,60)

    def _role_behaviour(self):
        if self.state==self.TRAVELLING:
            if self.has_arrived():
                self.state=self.next_state
                if self.state==self.AT_BEDSIDE: self.dwell_remaining=self.bedside_duration
                elif self.state==self.AT_WASHROOM: self.dwell_remaining=random.randint(5,10)
            return
        if self.state==self.AT_BEDSIDE:
            if self.dwell_remaining<=0:
                if random.random()<0.3 and self.set_path_to_room_type("washroom"):
                    self.state=self.TRAVELLING; self.next_state=self.AT_WASHROOM
                else: self._leave()
            return
        if self.state==self.AT_WASHROOM:
            if self.dwell_remaining<=0: self._leave()
            return
        if self.state==self.LEAVING:
            if self.has_arrived():
                self.model.remove_agent(self)
                return
            ents=self.model.floor_plan.entrances
            if ents and self.pos and _dist(self.pos,ents[0].position)<=self.ARRIVE_RADIUS_EXIT:
                self.entrance_stuck_ticks+=1
                if self.entrance_stuck_ticks>=ENTRANCE_STUCK_TIMEOUT:
                    self.model.remove_agent(self)
            return
    def _leave(self):
        self.state=self.LEAVING
        self.entrance_stuck_ticks=0
        ents=self.model.floor_plan.entrances
        if ents: self.set_path_to(ents[0].position)
        else: self.model.remove_agent(self)


#cleaners
class CleanerAgent(HospitalAgent):
    IN_ROOM="in_room"; TRAVELLING="travelling"
    def __init__(self, model):
        super().__init__(model,"cleaner"); self.state=self.TRAVELLING; self.cleaning_room=""
    
    def _find_target(self):
        counts={}
        for a in self.model._living_agents():
            if a.current_room_name: counts[a.current_room_name] = counts.get(a.current_room_name, 0) + 1
        best = None
        best_c =- 1
        for r in self.model.floor_plan.rooms:
            if "cleaner" not in r.access or r.name==self.current_room_name: 
                continue
            c = counts.get(r.name,0)
            if c > best_c: 
                best_c = c
                best = r.name
        return best
    def _role_behaviour(self):
        if self.state==self.TRAVELLING:
            if self.is_moving(): return
            if self.cleaning_room and self.has_arrived():
                self.state=self.IN_ROOM; self.dwell_remaining=random.randint(30,50)
            else:
                t=self._find_target()
                if t: self.cleaning_room=t; self.set_path_to_room(t)
            return
        if self.state==self.IN_ROOM:
            if self.dwell_remaining<=0:
                t=self._find_target()
                if t: self.cleaning_room=t; self.state=self.TRAVELLING; self.set_path_to_room(t)
                else: self.dwell_remaining=random.randint(30,50)
            return


#volunteer
class VolunteerAgent(HospitalAgent):
    AT_ROOM="at_room"; TRAVELLING="travelling"; LEAVING="leaving"
    def __init__(self, model):
        super().__init__(model,"volunteer"); self.state=self.TRAVELLING
        self.total_shift=random.randint(200,400); self.ticks=0
    def _role_behaviour(self):
        self.ticks+=1
        if self.ticks>=self.total_shift:
            if self.state!=self.LEAVING:
                self.state=self.LEAVING
                self.entrance_stuck_ticks=0
                ents=self.model.floor_plan.entrances
                if ents: self.set_path_to(ents[0].position)
            elif self.has_arrived():
                self.model.remove_agent(self)
            else:
                ents=self.model.floor_plan.entrances
                if ents and self.pos and _dist(self.pos,ents[0].position)<=self.ARRIVE_RADIUS_EXIT:
                    self.entrance_stuck_ticks+=1
                    if self.entrance_stuck_ticks>=ENTRANCE_STUCK_TIMEOUT:
                        self.model.remove_agent(self)
            return
        if self.state==self.TRAVELLING:
            if self.has_arrived(): self.state=self.AT_ROOM; self.dwell_remaining=random.randint(15,30)
            elif not self.is_moving():
                rooms=self.model.floor_plan.accessible_rooms("volunteer")
                if rooms: self.set_path_to_room(random.choice(rooms).name)
            return
        if self.state==self.AT_ROOM:
            if self.dwell_remaining<=0:
                rooms=self.model.floor_plan.accessible_rooms("volunteer")
                if rooms: self.state=self.TRAVELLING; self.set_path_to_room(random.choice(rooms).name)
            return

AGENT_CLASSES = {"patient":PatientAgent,"doctor":DoctorAgent,"nurse":NurseAgent,
    "visitor":VisitorAgent,"cleaner":CleanerAgent,"volunteer":VolunteerAgent}
