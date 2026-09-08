"""DocumentIR v1 shared by extraction, review and all output renderers.

Coordinates are visible-page, top-left points. Native Office anchors do not
invent page coordinates. Decimal values remain strings until export.
"""
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field


class IRModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class SourceAnchor(IRModel):
    method: str = "native"
    page_index: int | None = None
    bbox_pt: list[float] | None = None
    sheet: str | None = None
    cell: str | None = None
    block_id: str | None = None
    anchor_precision: Literal["cell", "block", "region", "page", "unknown"] = "unknown"


class Cell(IRModel):
    id: str
    row: int
    column: int
    rowspan: int = 1
    colspan: int = 1
    raw_text: str = ""
    display_text: str = ""
    value_kind: str = "text"
    value: Any = None
    resolution: str = "resolved"
    source: SourceAnchor = Field(default_factory=SourceAnchor)
    style: dict[str, Any] = Field(default_factory=dict)


class Table(IRModel):
    id: str
    title: str = ""
    row_count: int
    column_count: int
    header_rows: list[int] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    source: SourceAnchor = Field(default_factory=SourceAnchor)
    cells: list[Cell] = Field(default_factory=list)


class Block(IRModel):
    id: str
    kind: str = "paragraph"
    text: str = ""
    table_id: str | None = None
    source: SourceAnchor = Field(default_factory=SourceAnchor)
    style: dict[str, Any] = Field(default_factory=dict)


class Page(IRModel):
    page_index: int
    display_page_number: int
    width_pt: float
    height_pt: float
    rotation: int = 0
    classification: str = "native"
    coordinate_space: str = "visible-page-top-left-points"


class Issue(IRModel):
    id: str
    code: str
    message: str
    severity: str = "warning"
    target_id: str | None = None
    source: SourceAnchor = Field(default_factory=SourceAnchor)
    candidates: list[str] = Field(default_factory=list)
    status: str = "open"
    action: str = "查看原文并核对"


class DocumentIR(IRModel):
    schema_version: int = 1
    source_id: str = ""
    source_type: str
    pages: list[Page] = Field(default_factory=list)
    blocks: list[Block] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    engine_manifest: dict[str, Any] = Field(default_factory=dict)
    mappings: list[dict[str, Any]] = Field(default_factory=list)


class ToolError(Exception):
    def __init__(self, code: str, message: str, action: str = "请检查文件或调整设置后重试"):
        super().__init__(message)
        self.code, self.message, self.action = code, message, action


class Cancelled(ToolError):
    def __init__(self):
        super().__init__("CANCELLED", "任务已取消")


Progress = Callable[[str, int, int | None], None]
CancelCheck = Callable[[], bool]


class EngineResult:
    def __init__(self, ir: DocumentIR, files: list[dict[str, Any]],
                 summary: dict[str, Any] | None = None, quality: dict[str, Any] | None = None):
        self.ir, self.files = ir, files
        self.summary, self.quality = summary or {}, quality or {}


def result_file(path: Path, role: str = "result", filename: str | None = None) -> dict[str, Any]:
    return {"path": path, "role": role, "format": path.suffix.lstrip("."), "filename": filename or path.name}
