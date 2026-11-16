"""Explicit row outcomes: no silent dropping and no fictional score joins."""

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass

FIELDS = ("npi", "ind_enrl_id", "org_pac_id", "adrs_id", "pri_spec", "citytown", "state")
IDENTITY = FIELDS[:4]
STATES = set(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY AS GU MP PR VI AA AE AP FM MH PW".split()
)
KNOWN = set(FIELDS) | set(
    "ind_pac_id provider_last_name provider_first_name provider_middle_name suff gndr cred med_sch grd_yr sec_spec_1 sec_spec_2 sec_spec_3 sec_spec_4 sec_spec_all telehlth facility_name num_org_mem adr_ln_1 adr_ln_2 ln_2_sprs zip_code telephone_number ind_assgn grp_assgn".split()
)


class BatchError(Exception):
    """Safe operator-facing code; never embeds provider values or response bodies."""

    def __init__(self, code: str, received: int | None = None):
        self.code, self.received = code, received
        super().__init__(code)


def canonical(value) -> str:
    """Stable JSON for checksums; preserves duplicate rows when passed a list."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value) -> str:
    """SHA-256 content identity, not an authentication or de-identification claim."""
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def header_name(value: str) -> str:
    """CMS display headings to DKAN-style machine labels (City/Town -> citytown)."""
    return re.sub(r"[^a-z0-9_]", "", value.strip().lower().replace(" ", "_"))


@dataclass
class Validation:
    records: list[dict]
    findings: list[dict]
    valid: int
    rejected: int
    warnings: int


def validate(rows: list[dict], headers: list[str]) -> Validation:
    """Validate contract and rows, then reject every occurrence of duplicate identities."""
    if not rows:
        raise BatchError("empty_batch")
    if len(set(headers)) != len(headers) or not set(FIELDS).issubset(headers):
        raise BatchError("schema_missing_or_colliding_columns", len(rows))
    findings, records = [], []
    for extra in sorted(set(headers) - KNOWN):
        findings.append(dict(row_number=None, severity="warning", code="new_column", field=extra[:100]))
    for number, row in enumerate(rows, 1):
        if set(row) != set(FIELDS):
            raise BatchError("schema_row_shape", len(rows))
        data = {k: (v.strip() if isinstance(v, str) else "") for k, v in row.items()}
        errors = []

        def finding(field, code, severity="error"):
            findings.append(dict(row_number=number, severity=severity, code=code, field=field))
            if severity == "error":
                errors.append(code)

        for field in FIELDS:
            if not isinstance(row[field], str):
                finding(field, "invalid_type")
            if any(ord(c) < 32 for c in data[field]):
                finding(field, "control_character")
        if not re.fullmatch(r"[12][0-9]{9}", data["npi"]):
            finding("npi", "missing_identifier" if not data["npi"] else "invalid_identifier")
        if not re.fullmatch(r"[A-Za-z0-9]{15}", data["ind_enrl_id"]):
            finding("ind_enrl_id", "missing_identifier" if not data["ind_enrl_id"] else "invalid_identifier")
        if data["org_pac_id"] and not re.fullmatch(r"[0-9]{10}", data["org_pac_id"]):
            finding("org_pac_id", "invalid_identifier")
        if not 1 <= len(data["adrs_id"]) <= 25:
            finding("adrs_id", "missing_identifier" if not data["adrs_id"] else "invalid_identifier")
        for field, maximum in (("pri_spec", 60), ("citytown", 30)):
            if not data[field]:
                finding(field, "missing_optional", "warning")
            elif len(data[field]) > maximum:
                finding(field, "invalid_length")
        if not data["state"]:
            finding("state", "missing_optional", "warning")
        elif data["state"] not in STATES:
            finding("state", "invalid_state")
        # Keep the documented address key; do not reduce identity to NPI or city/state.
        key = digest([data[k] for k in IDENTITY])
        records.append(
            dict(
                row_number=number,
                record_key=key,
                accepted_key=None if errors else key,
                accepted=not errors,
                data=data,
                content_hash=digest(data),
            )
        )
    counts = Counter(r["record_key"] for r in records)
    for record in records:
        if counts[record["record_key"]] > 1:
            record.update(accepted=False, accepted_key=None)
            findings.append(
                dict(
                    row_number=record["row_number"],
                    severity="error",
                    code="duplicate_identity",
                    field="identity",
                )
            )
    valid = sum(r["accepted"] for r in records)
    return Validation(
        records, findings, valid, len(rows) - valid, sum(f["severity"] == "warning" for f in findings)
    )
