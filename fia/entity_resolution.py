from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher

from .db import Database
from .keying import classify_entity_name, name_block_key, normalize_name, organization_match_key

STRONG_IDENTIFIER_TYPES = {
    "company_number": "organization",
    "patent_number": "patent",
    "isrc": "recording",
}


@dataclass(frozen=True)
class ResolutionStats:
    entities: int
    memberships: int
    relations: int
    fuzzy_relations: int


def _soft_token(token: str) -> str:
    # Tiny deterministic stemmer for organization-name variants only. It deliberately avoids
    # aggressive linguistic stemming that could create surprising identity joins.
    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _soft_org_key(value: str) -> str:
    return " ".join(_soft_token(t) for t in organization_match_key(value).split())


def _name_similarity(a: str, b: str) -> float:
    ka = _soft_org_key(a)
    kb = _soft_org_key(b)
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 0.96
    seq = SequenceMatcher(None, ka, kb).ratio()
    ta, tb = set(ka.split()), set(kb.split())
    jaccard = len(ta & tb) / len(ta | tb) if ta | tb else 0.0
    return 0.72 * seq + 0.28 * jaccard


def _upsert_entity(
    conn: sqlite3.Connection,
    *,
    entity_type: str,
    canonical_key: str,
    display_name: str,
    confidence: float,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO entities(entity_type,canonical_key,display_name,confidence,created_at,updated_at)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(entity_type,canonical_key) DO UPDATE SET
          display_name=CASE
            WHEN length(excluded.display_name) > length(entities.display_name)
            THEN excluded.display_name ELSE entities.display_name END,
          confidence=max(entities.confidence, excluded.confidence),
          updated_at=excluded.updated_at
        """,
        (entity_type, canonical_key, display_name, confidence, now, now),
    )
    row = conn.execute(
        "SELECT id FROM entities WHERE entity_type=? AND canonical_key=?",
        (entity_type, canonical_key),
    ).fetchone()
    return int(row["id"])


def _add_membership(
    conn: sqlite3.Connection,
    *,
    entity_id: int,
    opportunity_id: int,
    role: str,
    match_method: str,
    confidence: float,
    evidence: dict,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO entity_memberships(
          entity_id,opportunity_id,role,match_method,confidence,evidence_json
        ) VALUES(?,?,?,?,?,?)
        """,
        (
            entity_id,
            opportunity_id,
            role,
            match_method,
            confidence,
            json.dumps(evidence, sort_keys=True, ensure_ascii=False),
        ),
    )


def _add_relation(
    conn: sqlite3.Connection,
    *,
    left_id: int,
    right_id: int,
    relation_type: str,
    confidence: float,
    evidence: dict,
) -> bool:
    if left_id == right_id:
        return False
    left_id, right_id = sorted((left_id, right_id))
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO entity_relations(
          left_entity_id,right_entity_id,relation_type,confidence,evidence_json,created_at
        ) VALUES(?,?,?,?,?,?)
        """,
        (
            left_id,
            right_id,
            relation_type,
            confidence,
            json.dumps(evidence, sort_keys=True, ensure_ascii=False),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    return cur.rowcount > 0


def rebuild_entity_graph(
    db: Database,
    *,
    fuzzy: bool = True,
    fuzzy_limit: int = 5000,
    min_fuzzy_score: float = 0.90,
) -> ResolutionStats:
    """Rebuild conservative entity/evidence graph from already-ingested public records.

    Strong identifiers become canonical entities. Exact normalized names become conservative
    name entities. Organization-name variants become reviewable relations, never automatic merges.
    Person-name fuzzy matching is deliberately disabled to reduce false identity linkage.
    """
    db.init()
    with db.connect() as conn:
        conn.execute("DELETE FROM entity_relations")
        conn.execute("DELETE FROM entity_memberships")
        conn.execute("DELETE FROM entities")
        # Keep entity IDs deterministic across graph rebuilds so persisted anomaly/research references
        # do not drift merely because the graph was recalculated.
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('entities','entity_relations')")

        # Strong identifier entities.
        strong_rows = conn.execute(
            """
            SELECT k.opportunity_id,k.key_type,k.key_value,o.source_id,o.external_id,o.title
            FROM opportunity_keys k
            JOIN opportunities o ON o.id=k.opportunity_id
            WHERE k.key_type IN ('company_number','patent_number','isrc')
            ORDER BY k.opportunity_id
            """
        )
        for row in strong_rows:
            entity_type = STRONG_IDENTIFIER_TYPES[row["key_type"]]
            entity_id = _upsert_entity(
                conn,
                entity_type=entity_type,
                canonical_key=f"{row['key_type']}:{row['key_value']}",
                display_name=row["key_value"],
                confidence=1.0,
            )
            _add_membership(
                conn,
                entity_id=entity_id,
                opportunity_id=int(row["opportunity_id"]),
                role="identifier",
                match_method="exact_identifier",
                confidence=1.0,
                evidence={"key_type": row["key_type"], "key_value": row["key_value"]},
            )

        # Exact owner-name entities. Same exact normalized name across sources shares one node,
        # but the confidence remains conservative because a name is not a unique legal identifier.
        name_rows = conn.execute(
            """
            SELECT o.id AS opportunity_id,o.owner_name,o.source_id,o.external_id
            FROM opportunities o
            WHERE o.owner_name IS NOT NULL AND trim(o.owner_name) <> ''
            ORDER BY o.id
            """
        )
        for row in name_rows:
            display = row["owner_name"]
            normalized = normalize_name(display)
            if len(normalized) < 4:
                continue
            entity_type = classify_entity_name(display)
            confidence = 0.90 if entity_type == "organization" else 0.70 if entity_type == "person" else 0.62
            entity_id = _upsert_entity(
                conn,
                entity_type=entity_type,
                canonical_key=f"name:{normalized}",
                display_name=display,
                confidence=confidence,
            )
            _add_membership(
                conn,
                entity_id=entity_id,
                opportunity_id=int(row["opportunity_id"]),
                role="owner_name",
                match_method="exact_normalized_name",
                confidence=confidence,
                evidence={"normalized_name": normalized},
            )

            # Official company sources may include prior names and registered-office data.
            # These become evidence relations, never automatic identity merges.
            raw_row = conn.execute(
                "SELECT raw_json FROM opportunities WHERE id=?", (int(row["opportunity_id"]),)
            ).fetchone()
            try:
                raw = json.loads(raw_row["raw_json"] or "{}") if raw_row else {}
            except json.JSONDecodeError:
                raw = {}
            if entity_type == "organization" and isinstance(raw, dict):
                prior_names = raw.get("previous_company_names") or []
                if isinstance(prior_names, list):
                    for prior in prior_names:
                        if not isinstance(prior, dict):
                            continue
                        alias = str(prior.get("name") or "").strip()
                        alias_norm = normalize_name(alias)
                        if len(alias_norm) < 4 or alias_norm == normalized:
                            continue
                        alias_id = _upsert_entity(
                            conn, entity_type="organization", canonical_key=f"name:{alias_norm}",
                            display_name=alias, confidence=0.96
                        )
                        _add_membership(
                            conn, entity_id=alias_id, opportunity_id=int(row["opportunity_id"]),
                            role="previous_company_name", match_method="source_asserted_alias",
                            confidence=0.96, evidence={"source": "official_company_record", "alias": alias}
                        )
                        _add_relation(
                            conn, left_id=entity_id, right_id=alias_id,
                            relation_type="previous_company_name_of", confidence=1.0,
                            evidence={"opportunity_id": int(row["opportunity_id"]), "source_asserted": True}
                        )

                address = raw.get("registered_office_address")
                if isinstance(address, dict):
                    parts = [str(address.get(k) or "").strip() for k in
                             ("premises", "address_line_1", "address_line_2", "locality", "region", "postal_code", "country")]
                    display_address = ", ".join(v for v in parts if v)
                    address_key = normalize_name(display_address)
                    if len(address_key) >= 5:
                        address_id = _upsert_entity(
                            conn, entity_type="address", canonical_key=f"address:{address_key}",
                            display_name=display_address, confidence=0.85
                        )
                        _add_membership(
                            conn, entity_id=address_id, opportunity_id=int(row["opportunity_id"]),
                            role="registered_office_address", match_method="source_asserted_address",
                            confidence=0.85, evidence={"postal_code": address.get("postal_code")}
                        )
                        _add_relation(
                            conn, left_id=entity_id, right_id=address_id,
                            relation_type="registered_office_at", confidence=1.0,
                            evidence={"opportunity_id": int(row["opportunity_id"]), "source_asserted": True}
                        )

        # Co-occurrence edges show that two entities/identifiers appeared in the same public record.
        opportunity_ids = conn.execute(
            "SELECT DISTINCT opportunity_id FROM entity_memberships ORDER BY opportunity_id"
        )
        for opp in opportunity_ids:
            entity_ids = [
                int(r["entity_id"])
                for r in conn.execute(
                    "SELECT DISTINCT entity_id FROM entity_memberships WHERE opportunity_id=? ORDER BY entity_id",
                    (int(opp["opportunity_id"]),),
                )
            ]
            for i, left in enumerate(entity_ids):
                for right in entity_ids[i + 1 :]:
                    _add_relation(
                        conn,
                        left_id=left,
                        right_id=right,
                        relation_type="co_occurs_in_source_record",
                        confidence=1.0,
                        evidence={"opportunity_id": int(opp["opportunity_id"])},
                    )

        # Research-result facts are durable evidence produced by completed read-only/manual research
        # tasks. Re-hydrate them after the opportunity graph so recursive research can add new edges
        # without converting those edges into opportunity ownership assertions.
        research_rows = list(conn.execute(
            """
            SELECT rf.*,rt.task_type,rt.anomaly_id
            FROM research_facts rf JOIN research_tasks rt ON rt.id=rf.task_id
            ORDER BY rf.id
            """
        ))
        for fact in research_rows:
            subject_id = _upsert_entity(
                conn,
                entity_type=str(fact["subject_entity_type"]),
                canonical_key=str(fact["subject_canonical_key"]),
                display_name=str(fact["subject_display_name"]),
                confidence=float(fact["confidence"]),
            )
            if fact["object_canonical_key"] and fact["object_entity_type"]:
                object_id = _upsert_entity(
                    conn,
                    entity_type=str(fact["object_entity_type"]),
                    canonical_key=str(fact["object_canonical_key"]),
                    display_name=str(fact["object_display_name"] or fact["object_canonical_key"]),
                    confidence=float(fact["confidence"]),
                )
                if fact["relation_type"]:
                    try:
                        evidence = json.loads(fact["evidence_json"] or "{}")
                    except (json.JSONDecodeError, TypeError):
                        evidence = {}
                    evidence.update({
                        "research_task_id": int(fact["task_id"]),
                        "research_source_id": str(fact["source_id"]),
                        "research_fact_type": str(fact["fact_type"]),
                        "research_derived": True,
                    })
                    _add_relation(
                        conn, left_id=subject_id, right_id=object_id,
                        relation_type=str(fact["relation_type"]),
                        confidence=float(fact["confidence"]), evidence=evidence,
                    )

        fuzzy_relations = 0
        if fuzzy and fuzzy_limit > 0:
            # Organization-only candidate generation. Rank entities with more source coverage first.
            candidates = list(
                conn.execute(
                    """
                    SELECT e.id,e.display_name,COUNT(DISTINCT o.source_id) AS source_count,
                           MAX(o.score) AS max_score
                    FROM entities e
                    JOIN entity_memberships m ON m.entity_id=e.id
                    JOIN opportunities o ON o.id=m.opportunity_id
                    WHERE e.entity_type='organization' AND e.canonical_key LIKE 'name:%'
                    GROUP BY e.id,e.display_name
                    ORDER BY source_count DESC,max_score DESC,e.id DESC
                    LIMIT ?
                    """,
                    (fuzzy_limit,),
                )
            )
            blocks: dict[str, list[sqlite3.Row]] = {}
            for row in candidates:
                block = name_block_key(row["display_name"])
                if block:
                    blocks.setdefault(block, []).append(row)

            for block, rows in blocks.items():
                # Pathological blocks are skipped instead of producing quadratic noise.
                if len(rows) > 80:
                    continue
                for i, left in enumerate(rows):
                    for right in rows[i + 1 :]:
                        score = _name_similarity(left["display_name"], right["display_name"])
                        if score < min_fuzzy_score:
                            continue
                        if _add_relation(
                            conn,
                            left_id=int(left["id"]),
                            right_id=int(right["id"]),
                            relation_type="possible_same_organization",
                            confidence=round(score, 4),
                            evidence={
                                "block": block,
                                "left_match_key": organization_match_key(left["display_name"]),
                                "right_match_key": organization_match_key(right["display_name"]),
                                "method": "organization_name_similarity",
                                "review_required": True,
                            },
                        ):
                            fuzzy_relations += 1

        counts = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM entities) AS entities,
              (SELECT COUNT(*) FROM entity_memberships) AS memberships,
              (SELECT COUNT(*) FROM entity_relations) AS relations
            """
        ).fetchone()
        conn.commit()
        return ResolutionStats(
            entities=int(counts["entities"]),
            memberships=int(counts["memberships"]),
            relations=int(counts["relations"]),
            fuzzy_relations=fuzzy_relations,
        )
