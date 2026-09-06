from typing import Literal

from pydantic import BaseModel


class WaterSignal(BaseModel):
    """A water-quality fact, reference, inference, or uncertainty."""

    kind: Literal[
        "observed_value",
        "supplied_reference_range",
        "inferred_pattern",
        "uncertainty",
    ]
    detail: str


class WaterQualityResult(BaseModel):
    """Structured result returned by the Water Quality Agent."""

    status: Literal[
        "normal",
        "watch",
        "elevated",
        "critical",
        "insufficient_information",
    ]
    key_signals: list[WaterSignal]
    explanation: str
    missing_information: list[str]
    monitoring_considerations: list[str]
