
from __future__ import annotations
import json, math, heapq
from typing import List, Dict, Tuple, Optional, Set

Point = Tuple[float, float]
Segment = Tuple[Point, Point]


def dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])

def point_in_polygon(point: Point, polygon: List[Point]) -> bool:
    x, y = point
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside

def polygon_centroid(polygon: List[Point]) -> Point:
    n = len(polygon)
    if n == 0:
        return (0.0, 0.0)
    return (sum(p[0] for p in polygon) / n, sum(p[1] for p in polygon) / n)

def _wall_crosses(a: Point, b: Point, wall: Segment) -> bool:

    p1, p2 = a, b
    p3, p4 = wall
    d1x, d1y = p2[0] - p1[0], p2[1] - p1[1]
    d2x, d2y = p4[0] - p3[0], p4[1] - p3[1]
    cross = d1x * d2y - d1y * d2x
    if abs(cross) < 1e-10:
        return False
    t = ((p3[0] - p1[0]) * d2y - (p3[1] - p1[1]) * d2x) / cross
    u = ((p3[0] - p1[0]) * d1y - (p3[1] - p1[1]) * d1x) / cross
    return 0.01 < t < 0.99 and -0.01 <= u <= 1.01



class Room:
    __slots__ = (
        "name", "room_type", "polygon", "centroid",
        "ventilation_ach", "volume_m3", "area_m2", "capacity",
        "ceiling_h", "access", "q_ventilation", "C_FF",
    )
    def __init__(self, name, room_type, polygon,
                 ventilation_ach=6.0, volume_m3=100.0, area_m2=40.0,
                 capacity=10, ceiling_h=2.7, access=None):
        self.name = name
        self.room_type = room_type
        self.polygon = [tuple(p) for p in polygon]
        self.centroid = polygon_centroid(self.polygon)
        self.ventilation_ach = ventilation_ach
        self.volume_m3 = volume_m3
        self.area_m2 = area_m2
        self.capacity = capacity
        self.ceiling_h = ceiling_h
        self.access = access if access is not None else [
            "patient", "doctor", "nurse", "visitor", "cleaner", "volunteer"
        ]
        self.q_ventilation = self.ventilation_ach * self.volume_m3
        self.C_FF = 0.0

    def contains(self, point):
        return point_in_polygon(point, self.polygon)

    def to_dict(self):
        return {"name": self.name, "room_type": self.room_type,
                "polygon": self.polygon, "ventilation_ach": self.ventilation_ach,
                "volume_m3": self.volume_m3, "area_m2": self.area_m2,
                "capacity": self.capacity, "access": self.access}


class Door:
    __slots__ = ("position", "connects")
    def __init__(self, position, connects):
        self.position = tuple(position)
        self.connects = connects

class Bed:
    __slots__ = ("position", "room_name", "assigned_patient")
    def __init__(self, position, room_name=""):
        self.position = tuple(position)
        self.room_name = room_name
        self.assigned_patient = None  

class Entrance:
    __slots__ = ("position",)
    def __init__(self, position):
        self.position = tuple(position)

class NurseStation:
    __slots__ = ("position", "room_name")
    def __init__(self, position, room_name=""):
        self.position = tuple(position)
        self.room_name = room_name



class GridPathfinder:

    DIRS = [
        (0, -1, 1.0), (0, 1, 1.0), (-1, 0, 1.0), (1, 0, 1.0),
        (-1, -1, 1.414), (-1, 1, 1.414), (1, -1, 1.414), (1, 1, 1.414),
    ]

    def __init__(self, floor_plan: "FloorPlan", grid_size: int = 20):
        self.grid_size = grid_size
        self.cols = int(math.ceil(floor_plan.width / grid_size))
        self.rows = int(math.ceil(floor_plan.height / grid_size))
        self.walls = floor_plan.walls

        self.walkable = [[False] * self.cols for _ in range(self.rows)]
        self.cell_room: List[List[Optional[str]]] = [[None] * self.cols for _ in range(self.rows)]
        self.cell_access: List[List[Optional[List[str]]]] = [[None] * self.cols for _ in range(self.rows)]

        non_corridor_rooms = [r for r in floor_plan.rooms if r.room_type != "corridor"]
        corridor_rooms = [r for r in floor_plan.rooms if r.room_type == "corridor"]

        for gy in range(self.rows):
            for gx in range(self.cols):
                cx = gx * grid_size + grid_size / 2
                cy = gy * grid_size + grid_size / 2

                found = False
                for room in non_corridor_rooms:
                    if room.contains((cx, cy)):
                        self.walkable[gy][gx] = True
                        self.cell_room[gy][gx] = room.name
                        self.cell_access[gy][gx] = room.access
                        found = True
                        break

                if not found:

                    for room in corridor_rooms:
                        if room.contains((cx, cy)):
                            self.walkable[gy][gx] = True
                            self.cell_room[gy][gx] = room.name
                            self.cell_access[gy][gx] = room.access
                            found = True
                            break

        for door in floor_plan.doors:
            gx, gy = self.world_to_grid(door.position)
            if 0 <= gx < self.cols and 0 <= gy < self.rows:
                self.walkable[gy][gx] = True

        self._walls = self._split_walls_at_doors(
            floor_plan.walls, floor_plan.doors, gap=grid_size * 0.8
        )

    @staticmethod
    def _split_walls_at_doors(walls, doors, gap=15):
      
        import math as _m
        door_pts = [d.position for d in doors]
        split = []
        for a, b in walls:
            dx, dy = b[0]-a[0], b[1]-a[1]
            seg_len = _m.hypot(dx, dy)
            if seg_len < 1e-6:
                continue

            on_wall = []
            for dp in door_pts:
                t = max(0, min(1, ((dp[0]-a[0])*dx + (dp[1]-a[1])*dy) / (seg_len*seg_len)))
                proj = (a[0]+t*dx, a[1]+t*dy)
                if _m.hypot(dp[0]-proj[0], dp[1]-proj[1]) < 5:
                    on_wall.append(t)
            if not on_wall:
                split.append((a, b))
                continue
            on_wall.sort()
            ux, uy = dx/seg_len, dy/seg_len
            half = gap / 2.0
            prev_end = 0.0
            for t in on_wall:
                door_dist = t * seg_len
                seg_start = prev_end
                seg_end = door_dist - half
                if seg_end > seg_start + 2:
                    p1 = (a[0]+ux*seg_start, a[1]+uy*seg_start)
                    p2 = (a[0]+ux*seg_end, a[1]+uy*seg_end)
                    split.append((p1, p2))
                prev_end = door_dist + half
            if prev_end < seg_len - 2:
                p1 = (a[0]+ux*prev_end, a[1]+uy*prev_end)
                split.append((p1, b))
        return split

    def world_to_grid(self, pos: Point) -> Tuple[int, int]:
        gx = int(pos[0] / self.grid_size)
        gy = int(pos[1] / self.grid_size)
        return (max(0, min(self.cols - 1, gx)), max(0, min(self.rows - 1, gy)))

    def grid_to_world(self, gx: int, gy: int) -> Point:
        return (gx * self.grid_size + self.grid_size / 2,
                gy * self.grid_size + self.grid_size / 2)

    def _can_move(self, ax: int, ay: int, bx: int, by: int) -> bool:

        a = self.grid_to_world(ax, ay)
        b = self.grid_to_world(bx, by)
        for wall in self._walls:
            if _wall_crosses(a, b, wall):
                return False
        return True

    def find_path(self, start: Point, goal: Point,
                  agent_type: str = "") -> List[Point]:

        sx, sy = self.world_to_grid(start)
        gx, gy = self.world_to_grid(goal)

        if not self.walkable[gy][gx]:
            gx, gy = self._nearest_walkable(gx, gy)
            if gx < 0:
                return []

        if not self.walkable[sy][sx]:
            sx, sy = self._nearest_walkable(sx, sy)
            if sx < 0:
                return []

        if sx == gx and sy == gy:
            return [self.grid_to_world(gx, gy)]

        #A* search
        open_set = [(0.0, 0, sx, sy)] 
        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
        g_score: Dict[Tuple[int, int], float] = {(sx, sy): 0.0}
        counter = 1

        goal_world = self.grid_to_world(gx, gy)

        while open_set:
            _, _, cx, cy = heapq.heappop(open_set)

            if cx == gx and cy == gy:
                
                path = []
                cur = (gx, gy)
                while cur in came_from:
                    path.append(self.grid_to_world(cur[0], cur[1]))
                    cur = came_from[cur]
                path.reverse()
        
                path.append(goal)
                return path

            for dx, dy, cost in self.DIRS:
                nx, ny = cx + dx, cy + dy
                if nx < 0 or nx >= self.cols or ny < 0 or ny >= self.rows:
                    continue
                if not self.walkable[ny][nx]:
                    continue

                if agent_type and self.cell_access[ny][nx]:
                    if agent_type not in self.cell_access[ny][nx]:
                        continue

        
                if not self._can_move(cx, cy, nx, ny):
                    continue

                tentative_g = g_score.get((cx, cy), float("inf")) + cost
                if tentative_g < g_score.get((nx, ny), float("inf")):
                    came_from[(nx, ny)] = (cx, cy)
                    g_score[(nx, ny)] = tentative_g
                    nw = self.grid_to_world(nx, ny)
                    h = math.hypot(nw[0] - goal_world[0], nw[1] - goal_world[1]) / self.grid_size
                    heapq.heappush(open_set, (tentative_g + h, counter, nx, ny))
                    counter += 1

        return [] 

    def _nearest_walkable(self, gx: int, gy: int) -> Tuple[int, int]:

        for radius in range(1, max(self.cols, self.rows)):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    nx, ny = gx + dx, gy + dy
                    if 0 <= nx < self.cols and 0 <= ny < self.rows:
                        if self.walkable[ny][nx]:
                            return (nx, ny)
        return (-1, -1)



class FloorPlan:
    def __init__(self):
        self.rooms: List[Room] = []
        self.walls: List[Segment] = []
        self.doors: List[Door] = []
        self.beds: List[Bed] = []
        self.entrances: List[Entrance] = []
        self.nurse_stations: List[NurseStation] = []
        self.width: float = 800.0
        self.height: float = 600.0
        self.name: str = "Unnamed"
        self.grid: Optional[GridPathfinder] = None

    def room_at(self, point) -> Optional[Room]:
        for room in self.rooms:
            if room.contains(point):
                return room
        return None

    def rooms_by_type(self, room_type) -> List[Room]:
        return [r for r in self.rooms if r.room_type == room_type]

    def beds_in_room(self, room_name) -> List[Bed]:
        return [b for b in self.beds if b.room_name == room_name]

    def room_by_name(self, name) -> Optional[Room]:
        for r in self.rooms:
            if r.name == name:
                return r
        return None

    def accessible_rooms(self, agent_type) -> List[Room]:
        return [r for r in self.rooms if agent_type in r.access]

    def find_path(self, start, goal, agent_type="") -> List[Point]:

        if self.grid is None:
            return []
        return self.grid.find_path(start, goal, agent_type)

    @classmethod
    def from_dict(cls, data):
        fp = cls()
        fp.name = data.get("name", "Imported")
        fp.width = float(data.get("width", 800))
        fp.height = float(data.get("height", 600))
        default_ceiling = float(data.get("ceiling_h", 2.7))

        for rd in data.get("rooms", []):
            fp.rooms.append(Room(
                name=rd["name"], room_type=rd.get("room_type", "corridor"),
                polygon=[tuple(p) for p in rd["polygon"]],
                ventilation_ach=float(rd.get("ventilation_ach", 6.0)),
                volume_m3=float(rd.get("volume_m3", 100.0)),
                area_m2=float(rd.get("area_m2", 40.0)),
                capacity=int(rd.get("capacity", 10)),
                ceiling_h=float(rd.get("ceiling_h", default_ceiling)),
                access=rd.get("access", ["patient", "doctor", "nurse", "visitor", "cleaner", "volunteer"]),
            ))
        for wd in data.get("walls", []):
            fp.walls.append((tuple(wd["start"]), tuple(wd["end"])))
        for dd in data.get("doors", []):
            fp.doors.append(Door(tuple(dd["position"]), dd.get("connects", [])))
        for bd in data.get("beds", []):
            pos = tuple(bd["position"])
            bed = Bed(pos)
            room = fp.room_at(pos)
            if room:
                bed.room_name = room.name
            fp.beds.append(bed)
        for ed in data.get("entrances", []):
            fp.entrances.append(Entrance(tuple(ed["position"])))
        for ns in data.get("nurse_stations", []):
            pos = tuple(ns["position"])
            station = NurseStation(pos)
            room = fp.room_at(pos)
            if room:
                station.room_name = room.name
            fp.nurse_stations.append(station)

        grid_size = int(data.get("grid_size", 20))
        fp.grid = GridPathfinder(fp, grid_size=grid_size)
        return fp

    def to_dict(self):
        return {
            "name": self.name, "width": self.width, "height": self.height,
            "rooms": [r.to_dict() for r in self.rooms],
            "walls": [{"start": list(w[0]), "end": list(w[1])} for w in self.walls],
            "doors": [{"position": list(d.position), "connects": d.connects} for d in self.doors],
            "beds": [{"position": list(b.position)} for b in self.beds],
            "entrances": [{"position": list(e.position)} for e in self.entrances],
        }


def make_simple_hospital():

    rooms = [
        {"name": "Office 1",    "room_type": "ward",     "polygon": [[120,60],[380,60],[380,180],[120,180]],   "ventilation_ach": 6,  "area_m2": 78,  "volume_m3": 156, "ceiling_h": 2, "capacity": 10, "color": "#004aad", "access": ["patient","cleaner","doctor","nurse"]},
        {"name": "Office 2",    "room_type": "ward",     "polygon": [[380,60],[640,60],[640,180],[380,180]],   "ventilation_ach": 12, "area_m2": 78,  "volume_m3": 156, "ceiling_h": 2, "capacity": 10, "color": "#004aad", "access": ["patient","visitor","cleaner","doctor","nurse","volunteer"]},
        {"name": "Waiting room","room_type": "waiting",  "polygon": [[640,60],[880,60],[880,180],[640,180]],   "ventilation_ach": 7,  "area_m2": 72,  "volume_m3": 144, "ceiling_h": 2, "capacity": 15, "color": "#b1d2ff", "access": ["patient","visitor","cleaner","doctor","nurse","volunteer"]},
        {"name": "washroom",    "room_type": "washroom", "polygon": [[800,260],[880,260],[880,380],[800,380]], "ventilation_ach": 10, "area_m2": 24,  "volume_m3": 48,  "ceiling_h": 2, "capacity": 10, "color": "#f0883e", "access": ["patient","visitor","cleaner","doctor","nurse","volunteer"]},
        {"name": "ER",          "room_type": "ward",     "polygon": [[600,260],[800,260],[800,380],[600,380]], "ventilation_ach": 6,  "area_m2": 60,  "volume_m3": 120, "ceiling_h": 2, "capacity": 20, "color": "#004aad", "access": ["patient","visitor","cleaner","doctor","nurse","volunteer"]},
        {"name": "Ward 1",      "room_type": "ward",     "polygon": [[240,260],[600,260],[600,380],[240,380]], "ventilation_ach": 6,  "area_m2": 108, "volume_m3": 216, "ceiling_h": 2, "capacity": 20, "color": "#004aad", "access": ["patient","visitor","cleaner","doctor","nurse","volunteer"]},
        {"name": "x-ray",       "room_type": "procedure","polygon": [[120,260],[240,260],[240,380],[120,380]], "ventilation_ach": 6,  "area_m2": 36,  "volume_m3": 72,  "ceiling_h": 2, "capacity": 5,  "color": "#17048c", "access": ["patient","cleaner","doctor","nurse"]},
        {"name": "corridor",    "room_type": "corridor", "polygon": [[120,180],[880,180],[880,260],[120,260]], "ventilation_ach": 6,  "area_m2": 152, "volume_m3": 304, "ceiling_h": 2, "capacity": 30, "color": "#d3e65c", "access": ["patient","visitor","cleaner","doctor","nurse","volunteer"]},
    ]
    walls = [
        {"start":[120,60],"end":[120,380]},{"start":[120,380],"end":[880,380]},
        {"start":[880,380],"end":[880,60]},{"start":[880,60],"end":[120,60]},
        {"start":[120,260],"end":[880,260]},{"start":[120,180],"end":[880,180]},
        {"start":[640,60],"end":[640,180]},{"start":[800,260],"end":[800,380]},
        {"start":[600,260],"end":[600,380]},{"start":[240,260],"end":[240,380]},
        {"start":[380,60],"end":[380,180]},
    ]
    doors = [
        {"position":[340,180],"connects":["corridor","Office 1"]},
        {"position":[180,260],"connects":["x-ray","corridor"]},
        {"position":[460,260],"connects":["Ward 1","corridor"]},
        {"position":[600,180],"connects":["corridor","Office 2"]},
        {"position":[800,180],"connects":["corridor","Waiting room"]},
        {"position":[840,260],"connects":["washroom","corridor"]},
        {"position":[700,260],"connects":["ER","corridor"]},
    ]
    beds = [
        {"position":[420,80]},{"position":[480,80]},{"position":[540,80]},{"position":[600,80]},
        {"position":[640,360]},{"position":[700,360]},{"position":[760,360]},
        {"position":[760,300]},{"position":[640,300]},
        {"position":[280,360]},{"position":[340,360]},{"position":[400,360]},
        {"position":[460,360]},{"position":[520,360]},{"position":[580,360]},
        {"position":[280,280]},{"position":[340,280]},{"position":[400,280]},
        {"position":[520,280]},{"position":[580,280]},
        {"position":[160,80]},{"position":[220,80]},{"position":[280,80]},{"position":[340,80]},
        {"position":[180,360]},
    ]
    return {"name": "Simple Hospital", "width": 1000, "height": 440, "ceiling_h": 2,
            "rooms": rooms, "walls": walls, "doors": doors, "beds": beds,
            "entrances": [{"position": [880, 220]}], "grid_size": 20}


def make_medium_hospital():

    rooms = [
        {"name": "ER",          "room_type": "ward",       "polygon": [[20,20],[400,20],[400,160],[20,160]],    "ventilation_ach": 14, "area_m2": 133, "volume_m3": 465.5, "ceiling_h": 3.5, "capacity": 30, "color": "#004aad", "access": ["patient","visitor","cleaner","doctor","nurse","volunteer"]},
        {"name": "Waiting Room","room_type": "waiting",    "polygon": [[20,260],[240,260],[240,420],[20,420]],  "ventilation_ach": 6,  "area_m2": 88,  "volume_m3": 308.0, "ceiling_h": 3.5, "capacity": 10, "color": "#b1d2ff", "access": ["patient","visitor","cleaner","doctor","nurse","volunteer"]},
        {"name": "Washroom 1",  "room_type": "washroom",   "polygon": [[400,20],[500,20],[500,80],[400,80]],    "ventilation_ach": 2,  "area_m2": 15,  "volume_m3": 52.5,  "ceiling_h": 3.5, "capacity": 10, "color": "#f0883e", "access": ["patient","visitor","cleaner","doctor","nurse","volunteer"]},
        {"name": "Washroom 2",  "room_type": "washroom",   "polygon": [[500,20],[600,20],[600,80],[500,80]],    "ventilation_ach": 10, "area_m2": 15,  "volume_m3": 52.5,  "ceiling_h": 3.5, "capacity": 10, "color": "#f0883e", "access": ["patient","visitor","cleaner","doctor","nurse","volunteer"]},
        {"name": "Ward 1",      "room_type": "ward",       "polygon": [[600,20],[980,20],[980,160],[600,160]],  "ventilation_ach": 15, "area_m2": 133, "volume_m3": 465.5, "ceiling_h": 3.5, "capacity": 40, "color": "#004aad", "access": ["patient","visitor","cleaner","doctor","nurse","volunteer"]},
        {"name": "Staff Room",  "room_type": "staff_room", "polygon": [[840,160],[980,160],[980,260],[840,260]],"ventilation_ach": 6,  "area_m2": 35,  "volume_m3": 122.5, "ceiling_h": 3.5, "capacity": 20, "color": "#cb6ce6", "access": ["cleaner","doctor","nurse"]},
        {"name": "Ward 2",      "room_type": "ward",       "polygon": [[440,260],[980,260],[980,420],[440,420]],"ventilation_ach": 6,  "area_m2": 216, "volume_m3": 756.0, "ceiling_h": 3.5, "capacity": 55, "color": "#004aad", "access": ["patient","cleaner","doctor","nurse"]},
        {"name": "ICU",         "room_type": "icu",        "polygon": [[240,320],[440,320],[440,420],[240,420]],"ventilation_ach": 12, "area_m2": 50,  "volume_m3": 175.0, "ceiling_h": 3.5, "capacity": 10, "color": "#f85149", "access": ["patient","cleaner","doctor","nurse"]},
        {"name": "Corridor",    "room_type": "corridor",   "polygon": [[20,260],[20,160],[400,160],[400,80],[600,80],[600,160],[840,160],[840,260],[440,260],[440,320],[240,320],[240,260]], "ventilation_ach": 6, "area_m2": 275, "volume_m3": 962.5, "ceiling_h": 3.5, "capacity": 60, "color": "#d3e65c", "access": ["patient","visitor","cleaner","doctor","nurse","volunteer"]},
    ]
    walls = [
        {"start":[20,20],"end":[980,20]},{"start":[980,20],"end":[980,420]},
        {"start":[980,420],"end":[20,420]},{"start":[20,420],"end":[20,20]},
        {"start":[20,160],"end":[400,160]},{"start":[400,160],"end":[400,20]},
        {"start":[400,80],"end":[600,80]},{"start":[600,80],"end":[600,20]},
        {"start":[600,80],"end":[600,160]},{"start":[600,160],"end":[980,160]},
        {"start":[20,260],"end":[240,260]},{"start":[240,260],"end":[240,420]},
        {"start":[500,20],"end":[500,80]},{"start":[440,260],"end":[440,420]},
        {"start":[440,260],"end":[600,260]},{"start":[600,260],"end":[980,260]},
        {"start":[840,160],"end":[840,260]},{"start":[240,320],"end":[440,320]},
    ]
    doors = [
        {"position":[120,260],"connects":["Waiting Room","Corridor"]},
        {"position":[340,320],"connects":["ICU","Corridor"]},
        {"position":[500,260],"connects":["Ward 2","Corridor"]},
        {"position":[640,160],"connects":["Corridor","Ward 1"]},
        {"position":[840,220],"connects":["Staff Room","Corridor"]},
        {"position":[440,80],"connects":["Corridor","Washroom 1"]},
        {"position":[560,80],"connects":["Corridor","Washroom 2"]},
        {"position":[400,120],"connects":["Corridor","ER"]},
        {"position":[200,160],"connects":["Corridor","ER"]},
    ]
    beds = [
        {"position":[60,40]},{"position":[100,40]},{"position":[140,40]},{"position":[180,40]},
        {"position":[220,40]},{"position":[260,40]},{"position":[300,40]},{"position":[340,40]},{"position":[380,40]},
        {"position":[340,140]},{"position":[300,140]},{"position":[260,140]},
        {"position":[160,140]},{"position":[120,140]},{"position":[80,140]},{"position":[40,140]},
        {"position":[260,400]},{"position":[300,400]},{"position":[340,400]},{"position":[380,400]},
        {"position":[420,400]},{"position":[480,400]},{"position":[520,400]},{"position":[560,400]},
        {"position":[600,400]},{"position":[640,400]},{"position":[680,400]},{"position":[720,400]},
        {"position":[760,400]},{"position":[800,400]},{"position":[840,400]},{"position":[880,400]},
        {"position":[920,400]},{"position":[960,400]},
        {"position":[960,280]},{"position":[960,320]},{"position":[960,360]},{"position":[920,280]},
        {"position":[560,280]},{"position":[600,280]},{"position":[640,280]},{"position":[680,280]},
        {"position":[720,280]},{"position":[760,280]},{"position":[800,280]},{"position":[840,280]},{"position":[880,280]},
        {"position":[680,140]},{"position":[720,140]},{"position":[760,140]},{"position":[800,140]},
        {"position":[840,140]},{"position":[880,140]},{"position":[920,140]},{"position":[960,140]},
        {"position":[960,100]},{"position":[960,60]},
        {"position":[920,40]},{"position":[880,40]},{"position":[840,40]},{"position":[800,40]},
        {"position":[760,40]},{"position":[720,40]},{"position":[680,40]},{"position":[640,40]},
    ]
    return {"name": "Medium Hospital", "width": 1000, "height": 440, "ceiling_h": 3.5,
            "rooms": rooms, "walls": walls, "doors": doors, "beds": beds,
            "entrances": [{"position": [20, 220]}], "grid_size": 20}


def make_complex_hospital():

    rooms = [
        {"name":"Reception",  "room_type":"reception", "polygon":[[160,180],[200,180],[200,260],[160,260]], "ventilation_ach":6,  "volume_m3":21.6,  "area_m2":8,   "capacity":4,  "access":["cleaner","doctor","nurse"]},
        {"name":"Corridor",   "room_type":"corridor",  "polygon":[[60,140],[800,140],[800,300],[60,300]], "ventilation_ach":4, "volume_m3":486, "area_m2":180, "capacity":50, "access":["patient","visitor","cleaner","doctor","nurse","volunteer"]},
        {"name":"ER",         "room_type":"ward",      "polygon":[[60,40],[300,40],[300,140],[60,140]],    "ventilation_ach":6,  "volume_m3":162,   "area_m2":60,  "capacity":30, "access":["patient","visitor","cleaner","doctor","nurse","volunteer"]},
        {"name":"waiting room","room_type":"waiting",  "polygon":[[60,300],[200,300],[200,400],[60,400]],  "ventilation_ach":2.5,"volume_m3":94.5,  "area_m2":35,  "capacity":20, "access":["patient","visitor","cleaner","doctor","nurse","volunteer"]},
        {"name":"staff room", "room_type":"staff_room","polygon":[[200,180],[400,180],[400,260],[200,260]],"ventilation_ach":6,  "volume_m3":108,   "area_m2":40,  "capacity":15, "access":["cleaner","doctor","nurse"]},
        {"name":"Ward A",     "room_type":"ward",      "polygon":[[300,40],[700,40],[700,140],[300,140]],  "ventilation_ach":6,  "volume_m3":270,   "area_m2":100, "capacity":32, "access":["patient","visitor","cleaner","doctor","nurse","volunteer"]},
        {"name":"ICU",        "room_type":"icu",       "polygon":[[700,40],[940,40],[940,140],[700,140]],  "ventilation_ach":10, "volume_m3":162,   "area_m2":60,  "capacity":12, "access":["patient","cleaner","doctor","nurse"]},
        {"name":"Office 1",   "room_type":"office",    "polygon":[[200,300],[400,300],[400,400],[200,400]],"ventilation_ach":6,  "volume_m3":135,   "area_m2":50,  "capacity":2,  "access":["patient","cleaner","doctor","nurse"]},
        {"name":"Office 2",   "room_type":"office",    "polygon":[[400,300],[600,300],[600,400],[400,400]],"ventilation_ach":6,  "volume_m3":135,   "area_m2":50,  "capacity":2,  "access":["patient","cleaner","doctor","nurse"]},
        {"name":"Ward B",     "room_type":"ward",      "polygon":[[600,300],[940,300],[940,400],[600,400]],"ventilation_ach":6,  "volume_m3":229.5, "area_m2":85,  "capacity":32, "access":["patient","visitor","cleaner","doctor","nurse","volunteer"]},
        {"name":"Washroom 1", "room_type":"washroom",  "polygon":[[600,180],[740,180],[740,220],[600,220]],"ventilation_ach":8,  "volume_m3":37.8,  "area_m2":14,  "capacity":10, "access":["patient","visitor","cleaner","doctor","nurse","volunteer"]},
        {"name":"Washroom 2", "room_type":"washroom",  "polygon":[[600,220],[740,220],[740,260],[600,260]],"ventilation_ach":8,  "volume_m3":37.8,  "area_m2":14,  "capacity":10, "access":["patient","visitor","cleaner","doctor","nurse","volunteer"]},
        {"name":"X-Ray",      "room_type":"procedure", "polygon":[[400,180],[500,180],[500,260],[400,260]],"ventilation_ach":6,  "volume_m3":54,    "area_m2":20,  "capacity":4,  "access":["patient","cleaner","doctor","nurse"]},
        {"name":"MRI",        "room_type":"procedure", "polygon":[[500,180],[600,180],[600,260],[500,260]],"ventilation_ach":10, "volume_m3":54,    "area_m2":20,  "capacity":4,  "access":["patient","cleaner","doctor","nurse"]},
        {"name":"Ward C",     "room_type":"ward",      "polygon":[[800,140],[940,140],[940,300],[800,300]],"ventilation_ach":20, "volume_m3":151.2, "area_m2":56,  "capacity":30, "access":["patient","visitor","cleaner","doctor","nurse","volunteer"]},
    ]
    walls = [
        {"start":[60,40],"end":[940,40]},{"start":[940,40],"end":[940,400]},{"start":[940,400],"end":[60,400]},{"start":[60,400],"end":[60,40]},
        {"start":[60,140],"end":[800,140]},{"start":[800,140],"end":[800,300]},{"start":[800,300],"end":[60,300]},
        {"start":[200,180],"end":[200,260]},{"start":[200,260],"end":[740,260]},{"start":[740,260],"end":[740,180]},{"start":[740,180],"end":[200,180]},
        {"start":[200,180],"end":[160,180]},{"start":[160,180],"end":[160,260]},{"start":[160,260],"end":[200,260]},
        {"start":[200,300],"end":[200,400]},{"start":[300,40],"end":[300,140]},{"start":[400,180],"end":[400,260]},
        {"start":[700,40],"end":[700,140]},{"start":[800,140],"end":[940,140]},{"start":[400,300],"end":[400,400]},
        {"start":[600,300],"end":[600,400]},{"start":[800,300],"end":[940,300]},
        {"start":[600,180],"end":[600,260]},{"start":[600,220],"end":[740,220]},{"start":[500,180],"end":[500,260]},
    ]
    doors = [
        {"position":[180,180],"connects":["Reception","Corridor"]},{"position":[180,260],"connects":["Reception","Corridor"]},
        {"position":[100,140],"connects":["ER","Corridor"]},{"position":[260,140],"connects":["ER","Corridor"]},
        {"position":[100,300],"connects":["waiting room","Corridor"]},{"position":[200,220],"connects":["Reception","staff room"]},
        {"position":[340,140],"connects":["Ward A","Corridor"]},{"position":[640,300],"connects":["Ward B","Corridor"]},
        {"position":[500,300],"connects":["Office 2","Corridor"]},{"position":[300,300],"connects":["Office 1","Corridor"]},
        {"position":[740,140],"connects":["Corridor","ICU"]},
        {"position":[740,200],"connects":["Washroom 1","Corridor"]},{"position":[740,240],"connects":["Washroom 2","Corridor"]},
        {"position":[560,180],"connects":["MRI","Corridor"]},{"position":[440,180],"connects":["X-Ray","Corridor"]},
        {"position":[800,220],"connects":["Ward C","Corridor"]},
    ]
    beds = [
        {"position":[340,60]},{"position":[380,60]},{"position":[420,60]},{"position":[460,60]},
        {"position":[500,60]},{"position":[540,60]},{"position":[580,60]},{"position":[620,60]},
        {"position":[620,120]},{"position":[580,120]},{"position":[540,120]},{"position":[500,120]},
        {"position":[460,120]},{"position":[420,120]},{"position":[660,60]},{"position":[660,120]},
        {"position":[740,60]},{"position":[800,60]},{"position":[860,60]},{"position":[920,60]},
        {"position":[920,120]},{"position":[860,120]},{"position":[800,120]},
        {"position":[920,320]},{"position":[920,380]},{"position":[880,320]},{"position":[880,380]},
        {"position":[840,320]},{"position":[840,380]},{"position":[800,320]},{"position":[800,380]},
        {"position":[760,320]},{"position":[760,380]},{"position":[700,320]},{"position":[700,380]},
        {"position":[640,380]},
        {"position":[100,60]},{"position":[160,60]},{"position":[220,60]},{"position":[280,60]},
        {"position":[160,120]},{"position":[220,120]},
        {"position":[820,160]},{"position":[860,160]},{"position":[900,160]},
        {"position":[920,200]},{"position":[920,240]},{"position":[920,280]},
        {"position":[880,280]},{"position":[840,280]},
    ]
    return {"name":"Complex Hospital","width":1000,"height":440,"ceiling_h":2.7,
            "rooms":rooms,"walls":walls,"doors":doors,"beds":beds,
            "entrances":[{"position":[60,220]}],"grid_size":20}



PREDEFINED = {"simple": make_simple_hospital, "medium": make_medium_hospital, "complex": make_complex_hospital}

def load_predefined(name):
    factory = PREDEFINED.get(name)
    if factory is None:
        raise ValueError(f"Unknown layout: {name}")
    return FloorPlan.from_dict(factory())

def load_from_json(json_path):
    with open(json_path, "r") as f:
        return FloorPlan.from_dict(json.load(f))
