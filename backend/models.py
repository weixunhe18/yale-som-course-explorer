"""Pydantic models for the Yale SOM course explorer.

Courses now come from the ``courses`` table rather than a JSON file. The columns
are already snake_case, so the alias gymnastics the JSON needed are gone — but the
values are still all TEXT (``units`` is "0.5", ``term_code`` is "20260902 000000.000"),
so the model keeps them as strings rather than coercing.

Note the table has no ``Bid Or Permission``, ``Visible`` or session start/end
columns; the JSON had them and the shipped database does not.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

import db as dbmod


class Course(BaseModel):
    """One row of the ``courses`` table."""

    model_config = ConfigDict(from_attributes=True, extra="ignore")

    row_id: int = 0
    course_id: str = ""
    number: str = ""
    title: str = ""
    section: str = ""
    category: str = ""
    course_type: str = ""
    description: str = ""
    units: str = ""

    faculty: str = ""
    faculty_email: str = ""
    faculty_bio: str = ""

    daytimes: str = ""
    day: str = ""
    start_time: str = ""
    end_time: str = ""
    room: str = ""

    session: str = ""
    term_code: str = ""
    syllabus: str = ""
    old_syllabus: str = ""

    @field_validator("*", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        # 79 rows carry Room=" " and a few carry padded titles/numbers; a lone space
        # is truthy everywhere downstream and renders as an empty field. NULL columns
        # become "" so the frontend never sees a null.
        if value is None:
            return ""
        return value.strip() if isinstance(value, str) else value

    @classmethod
    def from_row(cls, row: "dbmod.Course") -> "Course":
        """Build from a SQLAlchemy ``courses`` row."""
        return cls(
            row_id=row.id,
            course_id=row.course_id,
            number=row.course_number,
            title=row.course_title,
            section=row.section,
            category=row.course_category,
            course_type=row.course_type,
            description=row.course_description,
            units=row.units,
            faculty=row.faculty_1,
            faculty_email=row.faculty_1_email,
            faculty_bio=row.faculty_bio,
            daytimes=row.daytimes,
            day=row.timings_day,
            start_time=row.timings_start,
            end_time=row.timings_end,
            room=row.room,
            session=row.course_session,
            term_code=row.term_code,
            syllabus=row.syllabus,
            old_syllabus=row.old_syllabus,
        )

    def haystack(self) -> str:
        """Lowercased blob of the searchable fields, used for text matching."""
        return " ".join(
            (
                self.number,
                self.title,
                self.category,
                self.course_type,
                self.faculty,
                self.faculty_email,
                self.description,
                self.faculty_bio,
                self.daytimes,
                self.day,
                self.room,
                self.session,
            )
        ).lower()

    def summary(self) -> dict[str, Any]:
        """Compact form handed to the model — trimmed so tool output stays readable."""
        return {
            "number": self.number,
            "title": self.title,
            "section": self.section,
            "category": self.category,
            "units": self.units,
            "faculty": self.faculty,
            "faculty_email": self.faculty_email,
            "when": self.daytimes,
            "room": self.room,
            "session": self.session,
            "description": _clip(self.description, 600),
            "faculty_bio": _clip(self.faculty_bio, 400),
            "syllabus": self.syllabus,
        }


class CourseSearchResult(BaseModel):
    """What ``search_courses`` hands back to the agent."""

    query: str = ""
    filters: dict[str, str] = Field(default_factory=dict)
    total_matches: int = 0
    returned: int = 0
    truncated: bool = False
    courses: list[dict[str, Any]] = Field(default_factory=list)


class ToolCallRecord(BaseModel):
    """One tool invocation, as written to the audit trail."""

    tool: str
    kind: str = "function"
    args: dict[str, Any] = Field(default_factory=dict)
    result_preview: str = ""


class AuditEntry(BaseModel):
    """One full agent loop, appended to ``output/audit_trail.json``."""

    time: str
    model: str
    user_message: str
    thoughts: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    reply: str = ""
    tools_used: list[str] = Field(default_factory=list)
    stop_reason: str = ""
    usage: dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    """Return shape ``main.py`` expects from ``run_agent``."""

    reply: str
    tools_used: list[str] = Field(default_factory=list)


def _clip(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
