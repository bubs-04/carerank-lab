import { useState } from "react";
import { useApi } from "./api";
import type { Analytics, Provider } from "./types";

type Point = {
  id: number;
  name: string;
  avg_cost: number;
  quality: number;
  highlighted: boolean;
};
export type Cohort = {
  specialty: string;
  count: number;
  mean_cost: number | null;
  mean_score: number | null;
  items: Point[];
};
type EvidenceRow = {
  specialty: string;
  eligible: number;
  insufficient_outcomes: number;
  low_completeness: number;
  not_processed: number;
};
export type Evidence = {
  total: number;
  specialties: EvidenceRow[];
  completeness: { name: string; count: number }[];
};
const money = (n: number) =>
  n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });
const categories = [
  ["eligible", "Eligible", "#176e61"],
  ["insufficient_outcomes", "Fewer than 30 observed", "#b66a20"],
  ["low_completeness", "30+ observed; below 80% complete", "#536ba5"],
  ["not_processed", "Not processed / unavailable", "#6b7280"],
] as const;
const components = [
  ["outcome", "Outcome", 60],
  ["cost", "Cost", 25],
  ["reliability", "Reliability", 10],
  ["volume", "Volume", 5],
] as const;
const colors = ["#176e61", "#536ba5", "#b66a20"];
function Pending({ error }: { error: string }) {
  return (
    <p role={error ? "alert" : "status"}>
      {error
        ? `Unable to load analytics: ${error}. Retry using the navigation.`
        : "Loading analytics…"}
    </p>
  );
}
export function Scatter({
  data,
  open,
}: {
  data: Cohort;
  open: (ids: number[]) => void;
}) {
  const [active, setActive] = useState<Point | null>(null);
  if (!data.items.length)
    return (
      <p role="status">
        No eligible providers in this specialty. Missing evidence does not mean
        low quality.
      </p>
    );
  const maxCost = Math.max(1, ...data.items.map((p) => p.avg_cost)) * 1.08;
  const x = (cost: number) => 70 + (590 * cost) / maxCost;
  const y = (score: number) => 330 - score * 2.8;
  return (
    <>
      <p>
        {data.count} eligible providers · complete specialty cohort, independent
        of search pagination.
      </p>
      <p className="caption">
        Diamond: above the cohort mean score and below the cohort mean cost
        (strict inequalities). Circle: other eligible provider. Dashed lines
        mark cohort means.
      </p>
      <svg
        className="scatter"
        viewBox="0 0 720 400"
        role="group"
        aria-label={`Quality versus cost for ${data.specialty}. Interactive provider points. Equivalent table below.`}
      >
        {[0, 25, 50, 75, 100].map((n) => (
          <g key={n}>
            <line x1="70" x2="660" y1={y(n)} y2={y(n)} className="grid-line" />
            <text x="60" y={y(n) + 4} textAnchor="end">
              {n}
            </text>
          </g>
        ))}
        {[0, 0.25, 0.5, 0.75, 1].map((n) => (
          <g key={n}>
            <text x={x(maxCost * n)} y="352" textAnchor="middle">
              ${Math.round(maxCost * n).toLocaleString()}
            </text>
          </g>
        ))}
        <line x1="70" x2="660" y1="330" y2="330" stroke="#64748b" />
        <line x1="70" x2="70" y1="50" y2="330" stroke="#64748b" />
        {data.mean_cost !== null && (
          <line
            x1={x(data.mean_cost)}
            x2={x(data.mean_cost)}
            y1="50"
            y2="330"
            className="mean-line"
          />
        )}
        {data.mean_score !== null && (
          <line
            x1="70"
            x2="660"
            y1={y(data.mean_score)}
            y2={y(data.mean_score)}
            className="mean-line"
          />
        )}
        <text x="365" y="390" textAnchor="middle">
          Average synthetic encounter cost (USD, raw)
        </text>
        <text transform="translate(18 190) rotate(-90)" textAnchor="middle">
          Simulated quality score (0–100)
        </text>
        {data.items.map((p) => (
          <g
            key={p.id}
            role="button"
            tabIndex={0}
            aria-label={`Open ${p.name}, score ${p.quality.toFixed(2)}, cost ${money(p.avg_cost)}${p.highlighted ? ", above-mean score and below-mean cost" : ""}`}
            className="chart-point"
            onClick={() => open([p.id])}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                open([p.id]);
              }
            }}
            onMouseEnter={() => setActive(p)}
            onMouseLeave={() => setActive(null)}
            onFocus={() => setActive(p)}
            onBlur={() => setActive(null)}
          >
            <title>
              {p.name}: score {p.quality.toFixed(2)}, {money(p.avg_cost)}
            </title>
            <circle
              cx={x(p.avg_cost)}
              cy={y(p.quality)}
              r="9"
              fill="transparent"
            />
            {p.highlighted ? (
              <path
                d={`M ${x(p.avg_cost)} ${y(p.quality) - 6} l 6 6 -6 6 -6 -6 Z`}
                fill="#176e61"
              />
            ) : (
              <circle
                cx={x(p.avg_cost)}
                cy={y(p.quality)}
                r="4"
                fill="#536ba5"
                opacity=".75"
              />
            )}
          </g>
        ))}
      </svg>
      <div className="chart-tooltip" role="status" aria-live="polite">
        {active
          ? `${active.name} · Score ${active.quality.toFixed(2)} · ${money(active.avg_cost)} · Click or press Enter to open profile`
          : `Hover or focus a point. Mean score: ${data.mean_score?.toFixed(2)}; mean cost: ${money(data.mean_cost ?? 0)}.`}
      </div>
      <details>
        <summary>
          Accessible data table — all {data.count} eligible providers
        </summary>
        <div className="table-scroll">
          <table>
            <caption>{data.specialty} quality and raw cost</caption>
            <thead>
              <tr>
                <th>Provider</th>
                <th>Demo score</th>
                <th>Average cost</th>
                <th>Above-mean score / below-mean cost</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((p) => (
                <tr key={p.id}>
                  <td>
                    <button onClick={() => open([p.id])}>{p.name}</button>
                  </td>
                  <td>{p.quality.toFixed(2)}</td>
                  <td>{money(p.avg_cost)}</td>
                  <td>{p.highlighted ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </>
  );
}
export function EvidenceCharts({ data }: { data: Evidence }) {
  if (!data.total)
    return (
      <p role="status">
        No providers yet. Run the pipeline to populate evidence.
      </p>
    );
  const maximum = Math.max(1, ...data.completeness.map((b) => b.count));
  return (
    <>
      <section className="panel">
        <h2>Ranking eligibility by specialty</h2>
        <p>
          {data.total} providers. Each provider belongs to exactly one category.
        </p>
        <ul className="chart-legend">
          {categories.map(([key, label, color]) => (
            <li key={key}>
              <span style={{ background: color }} />
              {label}
            </li>
          ))}
        </ul>
        {data.specialties.map((row) => {
          const total = categories.reduce((n, [k]) => n + row[k], 0);
          return (
            <div className="evidence-row" key={row.specialty}>
              <strong>
                {row.specialty} · {total}
              </strong>
              <div
                className="stacked-bar"
                role="img"
                aria-label={categories
                  .map(([k, l]) => `${l}: ${row[k]}`)
                  .join("; ")}
              >
                {categories.map(([k, l, color]) => (
                  <div
                    key={k}
                    style={{
                      width: `${(100 * row[k]) / Math.max(1, total)}%`,
                      background: color,
                    }}
                    title={`${l}: ${row[k]}`}
                  >
                    {row[k] > 0 && <span>{row[k]}</span>}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
        <p className="caption">
          Fewer than 30 observed outcomes takes precedence, even if completeness
          is also below 80%. “Not processed / unavailable” includes absent
          scores or an unexpected unscored record. Missing evidence is not low
          quality.
        </p>
        <details>
          <summary>Eligibility counts in a table</summary>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Specialty</th>
                  {categories.map(([k, l]) => (
                    <th key={k}>{l}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.specialties.map((row) => (
                  <tr key={row.specialty}>
                    <th>{row.specialty}</th>
                    {categories.map(([k]) => (
                      <td key={k}>{row[k]}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </section>
      <section className="panel">
        <h2>Outcome completeness distribution</h2>
        <p>
          Observed outcomes divided by encounters. This measures evidence
          coverage, not outcome success.
        </p>
        <div className="bars">
          {data.completeness.map((b) => (
            <div key={b.name} className="bar-row">
              <span>{b.name}</span>
              <div
                className="bar-track"
                title={`${b.name}: ${b.count} providers`}
              >
                <div style={{ width: `${(b.count / maximum) * 100}%` }} />
              </div>
              <b>{b.count}</b>
            </div>
          ))}
        </div>
        <p className="caption">
          Intervals include the lower bound and exclude the upper bound, except
          80–100% includes 100%. No encounters has undefined completeness; not
          processed is separate. Counts total {data.total} providers.
        </p>
      </section>
    </>
  );
}
export function ComparisonChart({ providers }: { providers: Provider[] }) {
  return (
    <section className="panel">
      <h2>Component tradeoffs</h2>
      <p>
        Unweighted components on a shared 0–100 scale. Weights determine their
        contribution to the final score.
      </p>
      <ul className="chart-legend">
        {providers.map((p, i) => (
          <li key={p.id}>
            <span style={{ background: colors[i] }} />
            {p.name}
            {p.quality === null ? " (unscored)" : ""}
          </li>
        ))}
      </ul>
      <div className="component-groups">
        {components.map(([key, label, weight]) => (
          <div key={key} className="component-group">
            <h3>
              {label} · {weight}%
            </h3>
            {providers.map((p, i) => (
              <div key={p.id} className="component-chart-row">
                <span>{p.name}</span>
                <div
                  className="bar-track"
                  title={`${p.name}: ${p.components[key].toFixed(2)} × ${weight}% = ${((p.components[key] * weight) / 100).toFixed(2)} weighted points`}
                >
                  <div
                    style={{
                      width: `${p.components[key]}%`,
                      background: colors[i],
                    }}
                  />
                </div>
                <b>{p.components[key].toFixed(1)}</b>
              </div>
            ))}
          </div>
        ))}
      </div>
      <p className="caption">
        Higher cost-component values mean better normalized cost efficiency;
        they do not mean higher raw costs. Reliability and volume describe
        evidence. An unscored provider’s components remain descriptive and do
        not create a rank.
      </p>
      <div className="table-scroll">
        <table>
          <caption>
            Exact displayed components and weighted contributions (rounding may
            differ from final score)
          </caption>
          <thead>
            <tr>
              <th>Provider</th>
              {components.map(([k, l, w]) => (
                <th key={k}>
                  {l} ({w}%)
                  <br />
                  component → weighted points
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {providers.map((p) => (
              <tr key={p.id}>
                <th>{p.name}</th>
                {components.map(([k, , w]) => (
                  <td key={k}>
                    {p.components[k].toFixed(2)} →{" "}
                    {((p.components[k] * w) / 100).toFixed(2)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        Compare the bars: a 10-point outcome advantage adds 6 weighted points,
        while a 10-point cost advantage adds 2.5. A higher overall score can
        therefore coexist with a weaker cost component. Inspect the profiles
        below before interpreting that tradeoff.
      </p>
    </section>
  );
}
export default function AnalyticsPage({
  open,
}: {
  open: (ids: number[]) => void;
}) {
  const [specialty, setSpecialty] = useState("Cardiology");
  const meta = useApi<Analytics>("/api/analytics");
  const cohort = useApi<Cohort>(
    `/api/analytics/quality-cost?${new URLSearchParams({ specialty })}`,
  );
  const evidence = useApi<Evidence>("/api/analytics/evidence");
  return (
    <>
      <div className="heading">
        <div>
          <span className="eyebrow">COHORT ANALYTICS</span>
          <h1>Quality, cost, and evidence.</h1>
          <p>
            Explore patterns in fictional data, then inspect the underlying
            provider profile.
          </p>
        </div>
      </div>
      <section className="panel">
        <h2>Quality vs. cost explorer</h2>
        <label className="cohort-filter">
          Comparable specialty
          <select
            value={specialty}
            onChange={(e) => setSpecialty(e.target.value)}
          >
            {[
              ...new Set([
                specialty,
                ...(meta.data?.specialties.map((s) => s.name) ?? []),
              ]),
            ].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
        {meta.error && (
          <p role="alert">Specialty list unavailable: {meta.error}</p>
        )}
        <p className="caption">
          Lower raw costs or higher heuristic scores do not establish actual
          clinical superiority. Raw costs reflect procedure and risk mix; the
          scoring cost component uses normalized costs. Reference means describe
          this eligible cohort only.
        </p>
        {cohort.data ? (
          <Scatter key={specialty} data={cohort.data} open={open} />
        ) : (
          <Pending error={cohort.error} />
        )}
      </section>
      {evidence.data ? (
        <EvidenceCharts data={evidence.data} />
      ) : (
        <Pending error={evidence.error} />
      )}
    </>
  );
}
