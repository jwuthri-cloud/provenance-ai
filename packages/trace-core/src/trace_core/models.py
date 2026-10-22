"""The AuthorshipEvent — the immutable, content-addressed unit of provenance.

This is the open-standard surface (CC0). It is append-only: a human editing
AI-written code later produces its OWN event with `parent_event_id` lineage,
never a mutation of the original (docs/ARCHITECTURE.md §1, §3).
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .hashing import compute_event_id, content_hash as _content_hash

SCHEMA_VERSION = 1


class Source(str, Enum):
    """CC0 source taxonomy. `generated` and `inferred` are first-class so they are
    never silently miscredited as human or AI (review-fix, docs/ARCHITECTURE.md §3)."""

    human_keyboard = "human_keyboard"
    human_paste = "human_paste"
    cursor_autocomplete = "cursor_autocomplete"
    cursor_agent = "cursor_agent"
    claude_code_tool_call = "claude_code_tool_call"
    copilot_completion = "copilot_completion"
    copilot_agent = "copilot_agent"
    zed_agent = "zed_agent"
    ai_paste = "ai_paste"
    generated = "generated"
    inferred = "inferred"


class Operation(str, Enum):
    insert = "insert"
    replace = "replace"
    delete = "delete"
    create = "create"


class MatchKind(str, Enum):
    """How a chunk was followed across a diff (drives confidence + the `is_last_known`
    rendering state). Stages 1-2 land in M1, 3-5 in M2."""

    carry = "carry"
    move = "move"
    copy = "copy"
    edit = "edit"
    split = "split"
    merge = "merge"
    new = "new"
    line_fallback = "line_fallback"


class ContentRange(BaseModel):
    model_config = ConfigDict(frozen=True)
    start_line: int
    end_line: int

    @field_validator("start_line", "end_line")
    @classmethod
    def _positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("line numbers are 1-based (>= 1)")
        return v

    @model_validator(mode="after")
    def _ordered(self) -> "ContentRange":
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        return self


class HumanModifications(BaseModel):
    char_count: int = 0
    line_count: int = 0


class AuthorshipEvent(BaseModel):
    """One immutable authorship fact. Build via `AuthorshipEvent.create(...)` so the
    content hash and content-addressed id are computed canonically."""

    model_config = ConfigDict(use_enum_values=False)

    schema_version: int = SCHEMA_VERSION
    event_id: str
    timestamp: str  # RFC3339 / ISO8601 UTC
    source: Source
    model: Optional[str] = None
    session_id: Optional[str] = None
    prompt_hash: Optional[str] = None
    prompt_excerpt: Optional[str] = None  # redacted; encrypted at rest by the daemon vault
    file_path: str
    content_hash: str
    content_range: ContentRange
    operation: Operation
    match_kind: Optional[MatchKind] = None
    human_modifications_after: HumanModifications = Field(default_factory=HumanModifications)
    tool_calls: list[Any] = Field(default_factory=list)
    git_branch: Optional[str] = None
    repo_id: Optional[str] = None
    user_id: Optional[str] = None
    confidence: float = 1.0
    classifier_confidence: Optional[float] = None
    parent_event_id: Optional[str] = None
    prev_hash: Optional[str] = None

    def identity_core(self) -> dict:
        """The fields that DEFINE the fact and therefore the content-addressed id.

        Excludes derived/volatile fields (event_id, prev_hash, confidence,
        classifier_confidence, prompt_excerpt, human_modifications_after,
        match_kind, tool_calls) so two machines computing the same logical event
        get the same id."""
        return {
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "source": self.source.value,
            "model": self.model,
            "session_id": self.session_id,
            "prompt_hash": self.prompt_hash,
            "file_path": self.file_path,
            "content_hash": self.content_hash,
            "content_range": {
                "start_line": self.content_range.start_line,
                "end_line": self.content_range.end_line,
            },
            "operation": self.operation.value,
            "git_branch": self.git_branch,
            "repo_id": self.repo_id,
            "user_id": self.user_id,
        }

    @classmethod
    def create(
        cls,
        *,
        timestamp: str,
        source: Source | str,
        file_path: str,
        content_range: ContentRange | dict,
        operation: Operation | str,
        content: Optional[str] = None,
        content_hash: Optional[str] = None,
        model: Optional[str] = None,
        session_id: Optional[str] = None,
        prompt_hash: Optional[str] = None,
        prompt_excerpt: Optional[str] = None,
        git_branch: Optional[str] = None,
        repo_id: Optional[str] = None,
        user_id: Optional[str] = None,
        confidence: float = 1.0,
        classifier_confidence: Optional[float] = None,
        parent_event_id: Optional[str] = None,
        match_kind: Optional[MatchKind | str] = None,
        human_modifications_after: Optional[HumanModifications] = None,
        tool_calls: Optional[list] = None,
    ) -> "AuthorshipEvent":
        src = source if isinstance(source, Source) else Source(source)
        op = operation if isinstance(operation, Operation) else Operation(operation)
        cr = content_range if isinstance(content_range, ContentRange) else ContentRange(**content_range)
        if content_hash is None:
            if content is None:
                raise ValueError("AuthorshipEvent.create needs either `content` or `content_hash`")
            content_hash = _content_hash(content)

        identity = {
            "schema_version": SCHEMA_VERSION,
            "timestamp": timestamp,
            "source": src.value,
            "model": model,
            "session_id": session_id,
            "prompt_hash": prompt_hash,
            "file_path": file_path,
            "content_hash": content_hash,
            "content_range": {"start_line": cr.start_line, "end_line": cr.end_line},
            "operation": op.value,
            "git_branch": git_branch,
            "repo_id": repo_id,
            "user_id": user_id,
        }
        event_id = compute_event_id(identity)

        mk = None if match_kind is None else (match_kind if isinstance(match_kind, MatchKind) else MatchKind(match_kind))
        return cls(
            event_id=event_id,
            timestamp=timestamp,
            source=src,
            model=model,
            session_id=session_id,
            prompt_hash=prompt_hash,
            prompt_excerpt=prompt_excerpt,
            file_path=file_path,
            content_hash=content_hash,
            content_range=cr,
            operation=op,
            match_kind=mk,
            human_modifications_after=human_modifications_after or HumanModifications(),
            tool_calls=tool_calls or [],
            git_branch=git_branch,
            repo_id=repo_id,
            user_id=user_id,
            confidence=confidence,
            classifier_confidence=classifier_confidence,
            parent_event_id=parent_event_id,
        )
