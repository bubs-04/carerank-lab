"""Pure deterministic decisions. All thresholds use strictly greater than (>)."""

from dataclasses import asdict, dataclass
from ..ingestion.validation import digest
from .config import MonitoringSettings

CAVEAT = (
    "Source-order prefix only: cutoff shifts, address identity changes and rejected rows can alter "
    "membership. These are review signals, not national clinician entries/exits or clinical quality."
)


@dataclass(frozen=True)
class Rule:
    rule_id: str
    description: str
    severity: str
    threshold: float
    unit: str
    version: str = "1.0"

    @property
    def id(self):
        return digest(asdict(self))


def definitions(settings: MonitoringSettings) -> list[Rule]:
    """Return the complete ordered rule contract; changing a threshold creates a new hash."""
    rules = [
        Rule("attempt_failure", "Failed or interrupted completed ingestion", "critical", 0, "attempts"),
        Rule(
            "source_contract",
            "Recorded schema/provenance errors or new-column warnings",
            "critical",
            0,
            "findings",
        ),
        Rule(
            "rejected_rate",
            "Rejected rows as a percentage of received rows",
            "warning",
            settings.rejected_percent,
            "%",
        ),
        Rule(
            "duplicate_rate",
            "Rows involved in duplicate source identities / received rows",
            "critical",
            settings.duplicate_percent,
            "%",
        ),
    ]
    for field in ("pri_spec", "citytown", "state"):
        rules.append(
            Rule(
                f"missing_{field}",
                f"Rows with recorded missing {field} / received rows",
                "warning",
                settings.missing_percent,
                "%",
            )
        )
    rules.extend(
        [
            Rule(
                "warning_change",
                "Absolute change in warning findings per 100 received rows",
                "warning",
                settings.warning_rate_change,
                "findings / 100 rows",
            ),
            Rule(
                "accepted_change",
                "Absolute accepted-row change / baseline accepted rows",
                "warning",
                settings.accepted_change_percent,
                "%",
            ),
        ]
    )
    for kind in ("added", "removed", "changed"):
        rules.append(
            Rule(
                f"{kind}_rate",
                f"{kind.title()} accepted identities / union of accepted identities",
                "warning",
                settings.membership_percent,
                "% of union",
            )
        )
    return rules


def profile_id(rules: list[Rule]) -> str:
    return digest(sorted(rule.id for rule in rules))


def decide(rule: Rule, observed: float | None, evidence: dict, reason: str = "") -> dict:
    """None means unavailable, never zero. Equality passes; evidence retains exact counts."""
    if observed is None:
        return dict(status="not_evaluable", observed=None, explanation=reason, evidence=evidence)
    failed = observed > rule.threshold
    return dict(
        status="failed" if failed else "passed",
        observed=observed,
        explanation=f"{rule.description}: {observed:.4g} {rule.unit}; alert when > {rule.threshold:g}. {reason}".strip(),
        evidence=evidence,
    )
