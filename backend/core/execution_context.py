"""
Runtime Execution Context for pipeline stage tracking and telemetry.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from backend.core.control_context import ControlContext


@dataclass
class ExecutionContext:
    """
    Context created for a specific run/execution of an HLA Control pipeline.
    """
    control_context: ControlContext
    execution_id: str
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    status: str = "INITIALIZED"  # INITIALIZED, RUNNING, COMPLETED, FAILED
    stage_results: List[Dict[str, Any]] = field(default_factory=list)
    record_counts: Dict[str, int] = field(default_factory=dict)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    dry_run: bool = False

    def log_stage_completion(self, stage_name: str, entity_name: str, rows_affected: int, duration_sec: float):
        self.stage_results.append({
            "stage": stage_name,
            "entity": entity_name,
            "rows_affected": rows_affected,
            "duration_seconds": duration_sec,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        self.record_counts[f"{stage_name}:{entity_name}"] = rows_affected

    def mark_failed(self, error: Dict[str, Any]):
        self.status = "FAILED"
        self.end_time = datetime.now(timezone.utc)
        self.errors.append(error)

    def mark_completed(self):
        self.status = "COMPLETED"
        self.end_time = datetime.now(timezone.utc)
