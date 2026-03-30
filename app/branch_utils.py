"""Centralized branch constants, normalization, and DSM expansion.

Every part of the application that needs branch logic should import from here
rather than duplicating constants or expansion rules.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

# ── Canonical branch codes and labels ─────────────────────────────────────────

BRANCH_CHOICES: List[Dict[str, str]] = [
    {"code": "20GR", "label": "Grimes"},
    {"code": "25BW", "label": "Birchwood"},
    {"code": "40CV", "label": "Coralville"},
    {"code": "10FD", "label": "Fort Dodge"},
    {"code": "DSM", "label": "Des Moines Area"},
]

BRANCH_CODES: Tuple[str, ...] = tuple(b["code"] for b in BRANCH_CHOICES)

BRANCH_LABELS: Dict[str, str] = {b["code"]: b["label"] for b in BRANCH_CHOICES}

# DSM expands to Grimes + Birchwood
DSM_EXPANSION: List[str] = ["20GR", "25BW"]

# ── Legacy / alias mapping ────────────────────────────────────────────────────
# Maps lower-cased, stripped aliases to canonical branch codes.
# Includes dispatch-side GRIMES_AREA and various shorthand forms.

_ALIAS_MAP: Dict[str, Optional[str]] = {
    "all": None,
    "20gr": "20GR",
    "grimes": "20GR",
    "grimesarea": "20GR",
    "grimes_area": "20GR",
    "25bw": "25BW",
    "birchwood": "25BW",
    "10fd": "10FD",
    "fortdodge": "10FD",
    "40cv": "40CV",
    "coralville": "40CV",
    "dsm": "DSM",
    "desmoines": "DSM",
    "desmoinesarea": "DSM",
}

# Legacy dispatch values that should map to DSM (multi-branch expansion)
_DSM_ALIASES = frozenset({
    "grimes", "grimes_area", "grimesarea", "grimes area", "dsm",
    "desmoines", "desmoinesarea", "des moines area",
})


def normalize_branch(branch_id: Optional[str]) -> Optional[str]:
    """Normalize a branch identifier to its canonical code.

    Returns None for empty/falsy input or the ``all`` keyword.
    Unrecognised non-empty strings are uppercased as-is.
    """
    if not branch_id:
        return None
    compact = str(branch_id).strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    if not compact:
        return None
    mapped = _ALIAS_MAP.get(compact)
    if mapped is not None:
        return mapped
    if compact == "all":
        return None
    return str(branch_id).strip().upper()


def expand_branch(branch_code: Optional[str]) -> List[str]:
    """Expand a single canonical branch code into a list of codes.

    ``DSM`` expands to ``['20GR', '25BW']``; everything else returns a
    single-element list.  Returns empty list for ``None``.
    """
    if not branch_code:
        return []
    if branch_code == "DSM":
        return list(DSM_EXPANSION)
    return [branch_code]


def expand_branch_filter(raw: Optional[str]) -> List[str]:
    """Parse a comma-separated branch string and expand each entry.

    Handles legacy dispatch values like ``GRIMES_AREA`` by first normalizing,
    then expanding.  Returns a sorted unique list of canonical codes suitable
    for SQL ``IN`` clauses.
    """
    if not raw:
        return []
    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    result: list[str] = []
    for token in tokens:
        clean = token.strip().lower().replace("-", "").replace("_", "").replace(" ", "")
        # Check if this is a DSM alias that should expand to multiple branches
        if clean in {"grimes", "grimesarea", "dsm", "desmoines", "desmoinesarea"}:
            result.extend(DSM_EXPANSION)
        else:
            normalized = normalize_branch(token)
            if normalized:
                result.extend(expand_branch(normalized))
    return sorted(set(result))


def branch_label(code: Optional[str]) -> str:
    """Human-readable label for a branch code."""
    if not code:
        return "All Branches"
    return BRANCH_LABELS.get(code, code)


def is_valid_branch(code: Optional[str]) -> bool:
    """Check whether *code* is one of the canonical branch codes."""
    return code in BRANCH_LABELS


def sidebar_branch_choices() -> List[Dict[str, str]]:
    """Return the list of choices suitable for the sidebar dropdown.

    Includes an ``All Branches`` option with an empty code.
    """
    return [{"code": "", "label": "All Branches"}] + list(BRANCH_CHOICES)
