"""Pydantic mirrors of schemas/*.json.

The JSON files are what Gemini (and Agent Designer) see. These models validate every response
and also enforce constraints Gemini ignores. tests/test_schemas checks the two stay in sync.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Lane = Literal["patch", "retire", "fine", "unknown"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NormalizerOutput(_Strict):
    device_id: str
    vendor: Optional[str]
    product: Optional[str]
    model: Optional[str]
    version: Optional[str]
    confidence: float = Field(ge=0, le=1)
    lane: Literal["unknown", "pending_check"]
    needs_human: bool
    injection_detected: bool
    reason: str


class CheckerOutput(_Strict):
    device_id: str
    lane: Lane
    evidence_cve: list[str]
    evidence_lifecycle_id: Optional[str]
    due_date: Optional[dt.date]
    confidence: float = Field(ge=0, le=1)
    injection_detected: bool
    reason: str


class Message(_Strict):
    # No recipient: code sets it by rule (sim/guards.recipient), never the model.
    subject: str
    body: str


class Ticket(_Strict):
    create: bool
    existing_ticket_id: Optional[str]
    issue: Literal["patch", "retire", "identify"]


class PlannerOutput(_Strict):
    device_id: str
    lane: Lane
    action: Literal["notify_patch", "notify_retire", "ask_identify", "log_only"]
    priority: int = Field(ge=1, le=4)
    deadline: Optional[dt.date]
    requires_approval: bool
    escalate_to_human: bool
    message: Optional[Message]
    ticket: Optional[Ticket]
    injection_detected: bool
    reason: str


class VerifierOutput(_Strict):
    ticket_id: str
    device_id: str
    observed_change: Literal["device_removed", "version_changed", "no_change"]
    previous_version: Optional[str]
    current_version: Optional[str]
    decision: Literal["close", "remind", "escalate", "keep_open"]
    injection_detected: bool
    note: str


MODELS: dict[str, type[_Strict]] = {
    "normalizer": NormalizerOutput,
    "checker": CheckerOutput,
    "planner": PlannerOutput,
    "verifier": VerifierOutput,
}
