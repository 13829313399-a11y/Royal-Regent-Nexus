from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ReadResult:
    events: list[dict]
    cursor: dict
    rejected: list[dict]


class Adapter(Protocol):
    def probe(self) -> dict: ...
    def capabilities(self) -> dict: ...
    def read_snapshot(self) -> dict: ...
    def read_events_since(self, cursor: dict | None) -> ReadResult: ...
    def health(self) -> dict: ...


def capabilities(evidence):
    return dict(observeAvailability=True, observeRuntimeState=True, observeProgress=False, observeNativeJobId=True, observeCompletedJobs=True, observePieceCount=True, countUnit="unknown", observeInkUsage=False, inkEvidence="none", stageProductionFile=False, submitNativeJob=False, pauseNativeJob=False, cancelNativeJob=False, needsInteractiveSession=False, evidenceLevel=evidence, fixture_only=True)
