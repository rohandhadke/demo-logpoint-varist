from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel


class Risk(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Verdict(str, Enum):
    malicious = "malicious"
    suspicious = "suspicious"
    clean = "clean"
    unknown = "unknown"


class IOC(BaseModel):
    type: str
    value: str


class SubmitResponse(BaseModel):
    submission_id: str
    status: Literal["running"]


class ReportResponse(BaseModel):
    submission_id: str
    status: Literal["running", "done"]
    verdict: Optional[Verdict] = None
    risk: Optional[Risk] = None
    file_name: Optional[str] = None
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    scan_duration: Optional[float] = None
    reason: Optional[str] = None
    submitted: Optional[int] = None
    iocs: Optional[List[IOC]] = None

