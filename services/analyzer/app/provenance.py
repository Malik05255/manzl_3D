from __future__ import annotations

from .models import FloorPlan
from .topology import relink_plan_boundaries


def _changed_wall(before,after)->bool:
    return (
        before.a.x!=after.a.x or before.a.y!=after.a.y
        or before.b.x!=after.b.x or before.b.y!=after.b.y
        or before.thicknessPx!=after.thicknessPx
    )


def _changed_room(before,after)->bool:
    if before.name!=after.name or before.areaM2!=after.areaM2 or len(before.polygon)!=len(after.polygon):
        return True
    return any(
        left.x!=right.x or left.y!=right.y
        for left,right in zip(before.polygon,after.polygon)
    )


def _changed_opening(before,after)->bool:
    return (
        before.kind!=after.kind or before.wallId!=after.wallId
        or before.a.x!=after.a.x or before.a.y!=after.a.y
        or before.b.x!=after.b.x or before.b.y!=after.b.y
    )


def _ai_value(current:str|None)->str:
    if current in ("ai","manual","mixed"):
        return current if current=="mixed" else "mixed"
    return "mixed" if current else "ai"


def mark_ai_changes(before:FloorPlan,after:FloorPlan)->FloorPlan:
    before_walls={item.id:item for item in before.walls}
    for item in after.walls:
        previous=before_walls.get(item.id)
        if previous is None:
            item.provenance=item.provenance or "ai"
            continue
        if _changed_wall(previous,item):
            item.provenance=_ai_value(previous.provenance)

    before_rooms={item.id:item for item in before.rooms}
    for item in after.rooms:
        previous=before_rooms.get(item.id)
        if previous is None:
            item.provenance=item.provenance or "ai"
            continue
        if _changed_room(previous,item):
            item.provenance=_ai_value(previous.provenance)

    before_openings={item.id:item for item in [*before.doors,*before.windows]}
    for item in [*after.doors,*after.windows]:
        previous=before_openings.get(item.id)
        if previous is None:
            item.provenance=item.provenance or "ai"
            continue
        if _changed_opening(previous,item):
            item.provenance=_ai_value(previous.provenance)

    return relink_plan_boundaries(after)
