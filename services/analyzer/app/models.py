from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

class Point(BaseModel):
    x: float
    y: float

class Wall(BaseModel):
    id: str
    a: Point
    b: Point
    thicknessPx: float = 4.0
    confidence: float = Field(ge=0, le=1)

class Room(BaseModel):
    id: str
    name: str
    polygon: list[Point]
    confidence: float = Field(ge=0, le=1)
    areaM2: float | None = None

class Opening(BaseModel):
    id: str
    kind: Literal["door", "window"]
    wallId: str | None = None
    a: Point
    b: Point
    confidence: float = Field(ge=0, le=1)

class PlanLabel(BaseModel):
    id: str
    text: str
    center: Point
    confidence: float = Field(ge=0, le=1)
    kind: Literal["room_name", "dimension", "note", "unknown"]

class Quality(BaseModel):
    overall: float
    walls: float
    rooms: float
    text: float
    dimensions: float
    needsCalibration: bool
    warnings: list[str] = []

class Source(BaseModel):
    fileName: str
    mimeType: str
    page: int = 1

class FloorPlan(BaseModel):
    schemaVersion: Literal[1] = 1
    id: str
    widthPx: int
    heightPx: int
    metersPerPixel: float | None = None
    calibrationConfidence: float | None = None
    walls: list[Wall]
    rooms: list[Room]
    doors: list[Opening] = []
    windows: list[Opening] = []
    labels: list[PlanLabel]
    quality: Quality
    source: Source

class EditRequest(BaseModel):
    project_id: str
    command: str
    plan: FloorPlan

class ResizeRequest(BaseModel):
    project_id: str
    room_id: str
    width_m: float = Field(gt=0.5, le=50)
    height_m: float = Field(gt=0.5, le=50)
    plan: FloorPlan

class Impact(BaseModel):
    kind: Literal["room_resize", "room_remove", "wall_move", "door_move", "warning", "info"]
    text: str
    severity: Literal["info", "warning", "critical"] = "info"

class Proposal(BaseModel):
    id: str
    title: str
    summary: str
    confidence: float
    validationScore: float = Field(default=1.0, ge=0, le=1)
    impacts: list[Impact]
    warnings: list[str]
    previewPlan: FloorPlan

class ProposalResponse(BaseModel):
    command: str
    proposals: list[Proposal]
    needsClarification: str | None = None


class ValidationFinding(BaseModel):
    code: str
    severity: Literal["info", "warning", "critical"]
    text: str
    roomIds: list[str] = []

class ValidationReport(BaseModel):
    score: float = Field(ge=0, le=1)
    findings: list[ValidationFinding] = []

class ValidationRequest(BaseModel):
    project_id: str
    plan: FloorPlan
