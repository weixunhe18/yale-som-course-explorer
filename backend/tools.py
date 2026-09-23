"""Tools the course agent can call.

Only ``search_courses`` lives here. Web search is OpenAI's native tool, wired in
``agent.py`` as a provider capability rather than a Python function.

The search now runs against the ``courses`` table. Narrowing happens in SQL (each
query term must appear somewhere in the row, plus any category/faculty filter);
ranking and the day filter happen in Python, because "does this course meet on a
Thursday" needs the ``Daytimes`` parsing below and does not express well as SQL.
"""

from __future__ import annotations

import re

from sqlalchemy import func, or_, select

from db import Course as CourseRow
from db import get_session
from models import Course, CourseSearchResult

MAX_RESULTS = 15

# How a person might name a day -> canonical two-letter code.
_DAY_ALIASES = {
    "monday": "mo", "mon": "mo", "m": "mo", "mo": "mo",
    "tuesday": "tu", "tue": "tu", "tues": "tu", "t": "tu", "tu": "tu",
    "wednesday": "we", "wed": "we", "w": "we", "we": "we",
    "thursday": "th", "thu": "th", "thur": "th", "thurs": "th", "th": "th",
    "friday": "fr", "fri": "fr", "f": "fr", "fr": "fr",
    "saturday": "sa", "sat": "sa", "sa": "sa",
    "sunday": "su", "sun": "su", "su": "su",
}

# Codes as they appear inside "Daytimes", e.g. "T  Th 2:35 PM-3:55 PM".
# Matched as whole tokens so "T" (Tuesday) never swallows "Th" (Thursday).
_DAYTIME_CODES = {
    "m": "mo", "t": "tu", "w": "we", "th": "th", "f": "fr",
    "sa": "sa", "su": "su",
}

# The columns a free-text term is allowed to match, mirroring Course.haystack().
_SEARCH_COLUMNS = (
    CourseRow.course_number,
    CourseRow.course_title,
    CourseRow.course_category,
    CourseRow.course_type,
    CourseRow.faculty_1,
    CourseRow.faculty_1_email,
    CourseRow.course_description,
    CourseRow.faculty_bio,
    CourseRow.daytimes,
    CourseRow.timings_day,
    CourseRow.room,
    CourseRow.course_session,
)


def _normalize_day(value: str) -> str:
    return _DAY_ALIASES.get(value.strip().lower(), value.strip().lower())


def course_days(course: Course) -> set[str]:
    """Canonical day codes a course meets on.

    ``timings_day`` is populated for only ~11% of rows, so the meeting days really
    live in ``daytimes`` ("M  W 8:30 AM-9:50 AM"). Read both and union them.
    """
    days: set[str] = set()

    for token in re.split(r"[,\s]+", course.day.strip()):
        code = _DAY_ALIASES.get(token.lower())
        if code:
            days.add(code)

    # Take only the letters before the first digit: "T  Th 2:35 PM-3:55 PM" -> "T  Th"
    head = re.match(r"^([A-Za-z\s]+?)\s*(?=\d)", course.daytimes.strip())
    if head:
        for token in head.group(1).split():
            code = _DAYTIME_CODES.get(token.lower())
            if code:
                days.add(code)

    return days


def _like(column, needle: str):
    """Case-insensitive contains, and escape the LIKE wildcards in user input.

    Without the escape, a query of "100%" would match every row. SQLite's LIKE is
    already case-insensitive for ASCII but Postgres' is not, hence the explicit
    lower() on both sides.
    """
    safe = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return func.lower(func.coalesce(column, "")).like(f"%{safe.lower()}%", escape="\\")


def _score(course: Course, terms: list[str]) -> int:
    """Rank matches so an exact number/title hit beats a stray description mention."""
    if not terms:
        return 1

    number = course.number.lower()
    title = course.title.lower()
    faculty = course.faculty.lower()
    category = course.category.lower()
    haystack = course.haystack()

    total = 0
    for term in terms:
        if term not in haystack:
            return 0  # every term must appear somewhere
        if term == number or term.replace(" ", "") == number.replace(" ", ""):
            total += 100
        elif term in number:
            total += 40
        elif term in title:
            total += 30
        elif term in faculty:
            total += 25
        elif term in category:
            total += 15
        else:
            total += 5
    return total


def _fetch(terms: list[str], category: str, faculty: str) -> list[Course]:
    """Rows from ``courses`` matching every term plus the column filters."""
    stmt = select(CourseRow)

    for term in terms:
        # AND across terms, OR across the columns each term may appear in.
        stmt = stmt.where(or_(*[_like(col, term) for col in _SEARCH_COLUMNS]))
    if category:
        stmt = stmt.where(_like(CourseRow.course_category, category))
    if faculty:
        stmt = stmt.where(_like(CourseRow.faculty_1, faculty))

    with get_session() as session:
        return [Course.from_row(row) for row in session.scalars(stmt)]


def all_courses(query: str = "") -> list[Course]:
    """Every course, or those matching a free-text query. Used by ``/api/courses``."""
    terms = [t for t in query.lower().split() if t]
    rows = _fetch(terms, "", "")
    if terms:
        rows.sort(key=lambda c: (-_score(c, terms), c.number, c.section))
    else:
        rows.sort(key=lambda c: (c.number, c.section))
    return rows


def search_courses(
    query: str = "",
    category: str = "",
    faculty: str = "",
    day: str = "",
    limit: int = MAX_RESULTS,
) -> dict:
    """Search the Yale SOM course catalog.

    Args:
        query: Free text matched against course number, title, faculty, category,
            description, faculty bio, meeting time and room. Multiple words are ANDed.
        category: Restrict to a course category, e.g. "Finance", "Core", "Marketing".
        faculty: Restrict to an instructor name, e.g. "Simonsohn" or "Uri".
        day: Restrict to a meeting day, e.g. "Monday", "Mon", or "Mo".
        limit: Maximum courses to return (capped at 15).

    Returns:
        Matching courses with their number, title, faculty, meeting time, room,
        units, description and syllabus link.
    """
    terms = [t for t in query.lower().split() if t]
    day_needle = _normalize_day(day) if day else ""

    scored: list[tuple[int, Course]] = []
    for course in _fetch(terms, category.strip(), faculty.strip()):
        if day_needle and day_needle not in course_days(course):
            continue
        score = _score(course, terms)
        if score:
            scored.append((score, course))

    scored.sort(key=lambda pair: (-pair[0], pair[1].number, pair[1].section))

    capped = max(1, min(int(limit or MAX_RESULTS), MAX_RESULTS))
    top = scored[:capped]

    result = CourseSearchResult(
        query=query,
        filters={
            k: v
            for k, v in (
                ("category", category),
                ("faculty", faculty),
                ("day", day),
            )
            if v
        },
        total_matches=len(scored),
        returned=len(top),
        truncated=len(scored) > len(top),
        courses=[course.summary() for _, course in top],
    )
    return result.model_dump()
