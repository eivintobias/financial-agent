"""Shared data structures crossing the safety boundary.

These Pydantic models ARE the contract between zones: free-form client text
never crosses; only validated structured objects do.
"""
from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Dict, List

from pydantic import BaseModel, Field


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class TrustLevel(str, Enum):
    UNTRUSTED = "untrusted"
    SANITIZED = "sanitized"
    TRUSTED = "trusted"


class RiskTier(str, Enum):
    LOW = "low"        # read-only internal lookups
    MEDIUM = "medium"  # reversible internal writes / drafts
    HIGH = "high"      # irreversible or externally visible actions


class SanitizedContent(BaseModel):
    """Untrusted text AFTER sanitization. Still treated as data, never instructions."""

    text: str
    trust: TrustLevel = TrustLevel.SANITIZED
    source: str = ""
    flags: List[str] = Field(default_factory=list)


class ClientIntake(BaseModel):
    """Structured, validated output of the intake agent - the ONLY thing that
    crosses from the client-facing zone into the internal work zone."""

    request_id: str
    client_id: str
    category: str = "other"
    extracted: Dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    suggested_actions: List[str] = Field(default_factory=list)
    risk_flags: List[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    ok: bool
    reasons: List[str] = Field(default_factory=list)
    base_risk: RiskTier = RiskTier.MEDIUM


class ActionRequest(BaseModel):
    """A proposed tool call from the work agent. Must pass validation + risk gating."""

    action_id: str
    request_id: str
    client_id: str
    tool: str
    params: Dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""


class ExecutedAction(BaseModel):
    action_id: str
    tool: str
    risk: RiskTier
    status: str  # executed | pending_approval | rejected
    result: Dict[str, Any] = Field(default_factory=dict)
    detail: str = ""