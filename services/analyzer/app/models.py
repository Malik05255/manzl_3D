from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

class Point(BaseModel):
    x: float
    y: float

ElementProvenance = Literal["opencv","pdf-vector","ocr","cloud-ocr","pdf-text","manual","ai","mixed"]
WallRole = Literal["unknown","interior","exterior","structural"]

class Wall(BaseModel):
    id: str
    a: Point
    b: Point
    thicknessPx: float = 4.0
    confidence: float = Field(ge=0, le=1)
    heightM: float | None = Field(default=None, ge=0.5, le=20)
    role: WallRole = "unknown"
    locked: bool = False
    reviewed: bool = False
    provenance: ElementProvenance | None = None

class Room(BaseModel):
    id: str
    name: str
    polygon: list[Point]
    confidence: float = Field(ge=0, le=1)
    areaM2: float | None = None
    ceilingHeightM: float | None = Field(default=None, ge=0.5, le=20)
    boundaryWallIds: list[str] = Field(default_factory=list)
    reviewed: bool = False
    provenance: ElementProvenance | None = None

class Opening(BaseModel):
    id: str
    kind: Literal["door", "window"]
    doorSubtype: Literal["unknown","single_swing","double_swing","sliding"] | None = None
    doorSwingSide: Literal["positive","negative","unknown"] | None = None
    doorSwingDepthPx: float | None = Field(default=None, ge=0, le=30000)
    wallId: str | None = None
    a: Point
    b: Point
    confidence: float = Field(ge=0, le=1)
    heightM: float | None = Field(default=None, ge=0.2, le=10)
    sillHeightM: float | None = Field(default=None, ge=0, le=10)
    reviewed: bool = False
    provenance: ElementProvenance | None = None

class PlanSymbol(BaseModel):
    id: str
    kind: Literal["sink","toilet","bathtub","shower","cooktop","stairs"]
    a: Point
    b: Point
    confidence: float = Field(ge=0, le=1)
    reviewed: bool = False
    provenance: ElementProvenance | None = None

class PlanLabel(BaseModel):
    id: str
    text: str
    center: Point
    confidence: float = Field(ge=0, le=1)
    kind: Literal["room_name", "dimension", "note", "unknown"]
    reviewed: bool = False
    provenance: ElementProvenance | None = None

class Dimension(BaseModel):
    id: str
    sourceLabelId: str | None = None
    text: str
    center: Point
    valueM: float | None = Field(default=None, gt=0, le=1000)
    unit: Literal["m","cm","mm","unknown"] = "unknown"
    orientation: Literal["horizontal","vertical","unknown"] = "unknown"
    referenceWallId: str | None = None
    spanA: Point | None = None
    spanB: Point | None = None
    confidence: float = Field(ge=0, le=1)
    reviewed: bool = False
    provenance: ElementProvenance | None = None

class AnalysisMetadata(BaseModel):
    pipelineVersion: str
    analyzedAt: str
    sourceSha256: str
    engines: list[str] = []

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
    pageCount: int | None = None

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
    dimensions: list[Dimension] = []
    symbols: list[PlanSymbol] = []
    quality: Quality
    source: Source
    analysis: AnalysisMetadata | None = None

class EditRequest(BaseModel):
    project_id: str
    command: str
    plan: FloorPlan
    target_room_id: str | None = None
    target_wall_id: str | None = None
    target_opening_id: str | None = None

class ResizeRequest(BaseModel):
    project_id: str
    room_id: str
    width_m: float = Field(gt=0.5, le=50)
    height_m: float = Field(gt=0.5, le=50)
    plan: FloorPlan

class Impact(BaseModel):
    kind: Literal["room_resize", "room_remove", "wall_move", "wall_update", "door_move", "opening_update", "opening_remove", "warning", "info"]
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
    wallIds: list[str] = []
    openingIds: list[str] = []
    dimensionIds: list[str] = []

class ValidationReport(BaseModel):
    score: float = Field(ge=0, le=1)
    findings: list[ValidationFinding] = []

class ValidationRequest(BaseModel):
    project_id: str
    plan: FloorPlan

class CanonicalizeRequest(BaseModel):
    project_id: str
    plan: FloorPlan
