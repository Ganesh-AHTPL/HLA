"""
Control Context for runtime HLA execution and deployment.
Ensures no component derives or hardcodes control IDs (RULE 9, RULE 13).
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, Dict, Any, Union


@dataclass
class ControlContext:
    """
    Runtime context for an active HLA Control.
    Passed explicitly to parser, planner, DDL generator, SQL generator, validator, and executor.
    """
    control_id: Union[int, str]
    control_name: str
    hla_version: str = "1.0"
    target_schema: str = "ra_ctrl"
    execution_date: date = field(default_factory=date.today)
    execution_schedule: str = "DAILY"
    exec_seq: int = 1
    processing_date: date = field(default_factory=date.today)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Normalize control_id to ensure clean identifier formatting
        if isinstance(self.control_id, str):
            clean_id = self.control_id.strip()
            # If string is all digits, cast to int
            if clean_id.isdigit():
                self.control_id = int(clean_id)
            else:
                self.control_id = clean_id

    @property
    def control_id_str(self) -> str:
        """Returns standard string representation of control ID without spaces."""
        return str(self.control_id).replace(" ", "_").replace("-", "_").lower()

    @property
    def target_schema_name(self) -> str:
        """Returns the qualified target schema for this control."""
        if self.target_schema:
            return self.target_schema
        return f"ra_ctrl.ctrl_{self.control_id_str}"

    def format_table_name(self, pattern: str, entity: str = "") -> str:
        """
        Formats a table pattern dynamically using the active control context.
        Example: pattern='CTRL_{control_id}_SOURCE_DATASET_{entity}', entity='VDOM'
                 -> 'CTRL_23_SOURCE_DATASET_VDOM'
        """
        cid = str(self.control_id).upper()
        ent = str(entity).upper() if entity else ""
        return pattern.format(control_id=cid, entity=ent).rstrip("_")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "control_id": self.control_id,
            "control_name": self.control_name,
            "hla_version": self.hla_version,
            "target_schema": self.target_schema,
            "execution_date": self.execution_date.isoformat() if isinstance(self.execution_date, (date, datetime)) else str(self.execution_date),
            "execution_schedule": self.execution_schedule,
            "exec_seq": self.exec_seq,
            "processing_date": self.processing_date.isoformat() if isinstance(self.processing_date, (date, datetime)) else str(self.processing_date),
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ControlContext":
        exec_date = data.get("execution_date")
        if isinstance(exec_date, str):
            try:
                exec_date = date.fromisoformat(exec_date)
            except Exception:
                exec_date = date.today()
        elif not isinstance(exec_date, (date, datetime)):
            exec_date = date.today()

        proc_date = data.get("processing_date")
        if isinstance(proc_date, str):
            try:
                proc_date = date.fromisoformat(proc_date)
            except Exception:
                proc_date = date.today()
        elif not isinstance(proc_date, (date, datetime)):
            proc_date = date.today()

        return cls(
            control_id=data.get("control_id", 0),
            control_name=data.get("control_name", "Unknown Control"),
            hla_version=data.get("hla_version", "1.0"),
            target_schema=data.get("target_schema", "ra_ctrl"),
            execution_date=exec_date,
            execution_schedule=data.get("execution_schedule", "DAILY"),
            exec_seq=int(data.get("exec_seq", 1)),
            processing_date=proc_date,
            metadata=data.get("metadata", {})
        )
