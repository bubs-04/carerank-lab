"""Deterministic accepted-record comparisons; membership changes are sample-relative."""

from collections import Counter
from sqlalchemy import select
from .models import Snapshot, SourceRecord


def compare_records(old: list[dict], new: list[dict]) -> dict:
    """Partition accepted identities and enumerate exact tracked field changes."""
    left = {r["record_key"]: r["data"] for r in old if r["accepted"]}
    right = {r["record_key"]: r["data"] for r in new if r["accepted"]}
    if len(left) != sum(r["accepted"] for r in old) or len(right) != sum(r["accepted"] for r in new):
        raise ValueError("duplicate_accepted_identity")
    added, removed = sorted(right.keys() - left.keys()), sorted(left.keys() - right.keys())
    changes, field_counts = [], Counter()
    for key in sorted(left.keys() & right.keys()):
        fields = [
            f for f in sorted(left[key].keys() | right[key].keys()) if left[key].get(f) != right[key].get(f)
        ]
        if fields:
            field_counts.update(fields)
            changes.append({"record_key": key, "fields": fields, "before": left[key], "after": right[key]})
    return {
        "added": len(added),
        "removed": len(removed),
        "changed": len(changes),
        "unchanged": len(left.keys() & right.keys()) - len(changes),
        "specialty_changes": field_counts["pri_spec"],
        "location_changes": sum(bool(set(c["fields"]) & {"citytown", "state"}) for c in changes),
        "field_changes": dict(field_counts),
        "examples": changes[:50],
        "examples_truncated": len(changes) > 50,
        "added_examples": [{"record_key": k, "data": right[k]} for k in added[:20]],
        "removed_examples": [{"record_key": k, "data": left[k]} for k in removed[:20]],
    }


def records_for(db, snapshot_id: str) -> list[dict]:
    """At most configured 5,000 projected rows per version, never encounter data."""
    return [
        dict(record_key=r.record_key, data=r.data, accepted=r.accepted)
        for r in db.scalars(select(SourceRecord).where(SourceRecord.snapshot_id == snapshot_id))
    ]


def compare_versions(db, old_id: str, new_id: str) -> dict:
    """Reject incomparable source/scope/policy pairs, then include finding-count deltas."""
    old, new = db.get(Snapshot, old_id), db.get(Snapshot, new_id)
    if not old or not new:
        raise LookupError("snapshot_not_found")
    if (old.source_id, old.scope_hash, old.policy) != (new.source_id, new.scope_hash, new.policy):
        raise ValueError("incompatible_snapshot_scope_or_policy")
    result = compare_records(records_for(db, old_id), records_for(db, new_id))
    result.update(
        old_id=old_id,
        new_id=new_id,
        validation_delta={
            k: new.finding_counts.get(k, 0) - old.finding_counts.get(k, 0)
            for k in sorted(old.finding_counts.keys() | new.finding_counts.keys())
        },
        valid_delta=new.valid - old.valid,
        rejected_delta=new.rejected - old.rejected,
        caveat="Accepted-record membership in bounded samples only. A changed address key appears as removal/addition; a rejected row can also appear removed. Not national clinician exits or clinical quality.",
    )
    return result
