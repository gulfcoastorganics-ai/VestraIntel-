from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

PATENT_RE = re.compile(r"\b(?:RE\.?\s*)?\d{1,2},\d{3},\d{3}\b", re.I)
ISRC_RE = re.compile(r"\b[A-Z]{2}[A-Z0-9]{3}\d{7}\b", re.I)
COMPANY_CONTEXT_RE = re.compile(
    r"company[\s_-]*(?:number|no\.?)?[\"']?[\s_:#-]*[\"']?([A-Z]{0,2}\d{6,8})\b",
    re.I,
)

ORG_SUFFIXES = {
    "ag", "aps", "as", "bv", "co", "company", "corp", "corporation", "gmbh",
    "inc", "incorporated", "kg", "kk", "limited", "llc", "llp", "lp", "ltd",
    "nv", "oy", "plc", "pllc", "pte", "pty", "sa", "sas", "sarl", "spa",
}
ORG_HINTS = {
    "association", "bank", "college", "company", "corporation", "foundation", "fund",
    "group", "holdings", "hospital", "institute", "laboratories", "laboratory", "media",
    "partners", "press", "records", "services", "studio", "studios", "technologies",
    "technology", "university", "ventures",
}


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r"[^a-zA-Z0-9]+", " ", value).strip().lower()
    return " ".join(value.split())


def classify_entity_name(value: str) -> str:
    """Conservative coarse type used only for candidate blocking and confidence."""
    normalized = normalize_name(value)
    tokens = normalized.split()
    if not tokens:
        return "unknown"
    if tokens[-1] in ORG_SUFFIXES or any(token in ORG_HINTS for token in tokens):
        return "organization"
    # Do not infer that long/odd names are people. Person fuzzy matching is intentionally disabled.
    if 2 <= len(tokens) <= 5 and all(token.isalpha() for token in tokens):
        return "person"
    return "unknown"


def organization_match_key(value: str) -> str:
    normalized = normalize_name(value)
    tokens = normalized.split()
    if tokens and tokens[0] == "the":
        tokens = tokens[1:]
    while len(tokens) > 1 and tokens[-1] in ORG_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def name_block_key(value: str) -> str:
    """Cheap blocking key for organization-name candidate generation."""
    base = organization_match_key(value)
    tokens = base.split()
    if not tokens:
        return ""
    first = tokens[0]
    return f"{first[:5]}:{len(tokens)}"


def extract_keys(*, title: str, owner_name: str | None, raw_text: str = "") -> Iterable[tuple[str, str]]:
    if owner_name:
        normalized = normalize_name(owner_name)
        if len(normalized) >= 4:
            yield "owner_name", normalized
            entity_type = classify_entity_name(owner_name)
            yield "owner_type", entity_type
            if entity_type == "organization":
                match_key = organization_match_key(owner_name)
                if len(match_key) >= 3:
                    yield "owner_org_match", match_key
                    block = name_block_key(owner_name)
                    if block:
                        yield "owner_org_block", block

    blob = f"{title}\n{raw_text}"
    for patent in PATENT_RE.findall(blob):
        yield "patent_number", re.sub(r"\s+", "", patent.upper())
    for isrc in ISRC_RE.findall(blob.upper()):
        yield "isrc", isrc.upper()
    for match in COMPANY_CONTEXT_RE.finditer(blob):
        yield "company_number", match.group(1).upper()
