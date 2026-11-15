# Exercise Solutions

These are reference implementations to apply to the actual repository, not changes already included in the baseline.

## 1 Evidence label

Export a small component from App.tsx:

```tsx
export function EvidenceLabel({observed}:{observed:number}) {
  return observed < 50 ? <small>Limited evidence</small> : null;
}
```

Place `<EvidenceLabel observed={p.observed}/>` in the encounter table cell. In App.test.tsx, render with 49, assert the label is present, rerender with 50 and assert it is absent. This label is independent of the scoring eligibility rule; do not change the backend threshold.

## 2 Minimum observed outcomes

In the endpoint, append `min_observed: int | None = Query(None, ge=0)` and pass it as a named argument. Add `min_observed: int | None = None` at the end of `repository.search`. Before counting the query, apply:

```python
if min_observed is not None:
    query = query.where(Score.observed >= min_observed)
```

Using `is not None` preserves zero as a valid explicit bound. Add an Explorer state and number input, reset page to 1 on changes, and set the URLSearchParams key only when nonempty. Defaulted final arguments preserve existing callers, but inspect them anyway. Compare the API count with a direct SQL count and test `min_observed=-1` returns 422.

## 3 Immutable evidence policy

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class EvidencePolicy:
    minimum: int = 30
    strength: float = 50.0

    def __post_init__(self):
        if self.minimum < 1 or not math.isfinite(self.strength) or self.strength <= 0:
            raise ValueError("Invalid evidence policy")
```

Add `policy: EvidencePolicy = EvidencePolicy()` to `score_provider`; use `policy.minimum` and `policy.strength`. Store policy values with each score and change the algorithm version when policy changes. Test 39 versus 40 observed outcomes under minimum=40 and show that strength=100 moves the outcome component closer to 50 than strength=50. Never tune the policy merely to improve a preferred provider's rank.

## 4 Verify the actual prior snapshot

Before the injected failure, query `select(Score.provider_id, Score.quality).order_by(Score.provider_id)` into a list. After `pytest.raises(RuntimeError)`, run the same query on a new connection and assert exact equality. Also verify the newest PipelineRun has status `failed` and error `RuntimeError`. Monkeypatch `pipeline.score_provider` to raise, as the existing test does. If audit were inside the rolled-back transaction, evidence of the failed attempt would disappear.

## 5 Mean synthetic risk

Add nullable `mean_risk: Mapped[float | None] = mapped_column(Float)` to Score. Create migration `002_mean_risk.py` with revision `002`, down_revision `001`, upgrade `op.add_column("scores", sa.Column("mean_risk", sa.Float(), nullable=True))`, and downgrade `op.drop_column("scores", "mean_risk")`.

In aggregate.sql, select `AVG(n.risk) AS mean_risk`; do not coalesce no encounters to zero. In pipeline.py include `"mean_risk": a["mean_risk"]` in each stored row. Add the optional field to ProviderView, repository.serialize and the TypeScript Provider type, then render `p.mean_risk?.toFixed(3) ?? "No encounters"`. Independently query `SELECT AVG(risk) FROM encounters WHERE provider_id=:id` and compare with pytest.approx. Verify that existing score rows have NULL immediately after migration and values after a pipeline rerun. Run `alembic downgrade 001` then `alembic upgrade head` only on a disposable database. Risk is a simulated input, not evidence of treatment effect.
