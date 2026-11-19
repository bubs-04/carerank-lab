import DataOps from "./DataOps";
import PipelineOperations from "./PipelineOperations";
import Reliability from "./Reliability";
import AnalyticsPage, { ComparisonChart } from "./Analytics";
import { useState } from "react";
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  Database,
  Search,
  ShieldCheck,
  Users,
  GitCompareArrows,
  ArrowLeft,
  FlaskConical,
} from "lucide-react";
import { useApi } from "./api";
import type { Analytics, Provider, ProviderPage } from "./types";
const num = (n: number) => n.toLocaleString();
const money = (n: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
export function ScoreBadge({ value }: { value: number | null }) {
  return value === null ? (
    <span className="badge muted">Insufficient data</span>
  ) : (
    <span className="badge">
      {value.toFixed(1)} <small>/ 100</small>
    </span>
  );
}
function State({ error, loading }: { error: string; loading: boolean }) {
  return (
    <div className="state" role={error ? "alert" : "status"}>
      {error ? (
        <>
          <h3>We couldn’t load this view.</h3>
          <p>{error}</p>
          <button onClick={() => window.location.reload()}>Try again</button>
        </>
      ) : loading ? (
        "Loading provider intelligence…"
      ) : (
        "No records yet. Run the pipeline to populate this workspace."
      )}
    </div>
  );
}
function Bars({ items }: { items: { name: string; count: number }[] }) {
  const max = Math.max(1, ...items.map((x) => x.count));
  return (
    <div className="bars">
      {items.map((x) => (
        <div key={x.name} className="bar-row">
          <span>{x.name}</span>
          <div className="bar-track">
            <div style={{ width: `${(x.count / max) * 100}%` }} />
          </div>
          <b>{num(x.count)}</b>
        </div>
      ))}
    </div>
  );
}
function Overview({
  open,
  analyze,
}: {
  open: () => void;
  analyze: () => void;
}) {
  const { data, error, loading } = useApi<Analytics>("/api/analytics");
  if (!data) return <State error={error} loading={loading} />;
  return (
    <>
      <div className="heading">
        <div>
          <span className="eyebrow">THE BIG PICTURE</span>
          <h1>Provider intelligence, explained.</h1>
          <p>
            A clearer view of quality, cost, and the evidence behind every
            score.
          </p>
        </div>
        <div className="overview-actions">
          <button onClick={analyze}>Explore analytics</button>
          <button className="primary" onClick={open}>
            Explore providers <ArrowUpRight size={16} />
          </button>
        </div>
      </div>
      <div className="metrics">
        {[
          {
            label: "Providers analyzed",
            value: num(data.providers),
            note: "Across comparable specialties",
            Icon: Users,
          },
          {
            label: "Encounters processed",
            value: num(data.encounters),
            note: "Fictional, reproducible records",
            Icon: Activity,
          },
          {
            label: "Eligible for ranking",
            value: num(data.scored),
            note: "30+ observed · 80%+ completeness",
            Icon: ShieldCheck,
          },
          {
            label: "Mean demo score",
            value: data.mean_score?.toFixed(1) ?? "—",
            note: "Descriptive only • not a clinical rating",
            Icon: BarChart3,
          },
        ].map(({ label, value, note, Icon }) => (
          <section className="metric" key={label}>
            <div>
              {label}
              <Icon size={18} />
            </div>
            <strong>{value}</strong>
            <small>{note}</small>
          </section>
        ))}
      </div>
      <div className="two-col">
        <section className="panel">
          <div className="section-head">
            <div>
              <span className="eyebrow">COHORT COVERAGE</span>
              <h2>Specialty distribution</h2>
            </div>
            <span className="pill">Provider count</span>
          </div>
          <Bars items={data.specialties} />
        </section>
        <section className="panel">
          <div className="section-head">
            <div>
              <span className="eyebrow">SCORE LANDSCAPE</span>
              <h2>Quality score distribution</h2>
            </div>
            <BarChart3 size={20} />
          </div>
          <Bars items={data.distribution} />
          <p className="caption">
            Unscored providers excluded. These are demonstration measures.
          </p>
        </section>
      </div>
      <section className="pipeline">
        <div className="pipeline-icon">
          <Database />
        </div>
        <div>
          <span className="eyebrow">DATA PIPELINE</span>
          <h2>
            {data.latest_run
              ? `Latest run: ${data.latest_run.status}`
              : "Awaiting first run"}
          </h2>
          <p>
            Last successful refresh:{" "}
            {data.last_success?.finished_at
              ? new Date(data.last_success.finished_at).toLocaleString()
              : "No successful run yet"}
          </p>
        </div>
        <div className="duration">
          {data.latest_run?.seconds?.toFixed(2) ?? "—"}
          <small>seconds / latest run</small>
        </div>
      </section>
      <section className="method-callout">
        <FlaskConical />
        <div>
          <h3>Transparency is the point.</h3>
          <p>
            Simulated outcomes (60%), cost efficiency (25%), reliability (10%),
            and volume (5%). Compare within a specialty and inspect the evidence
            behind each score.
          </p>
        </div>
      </section>
    </>
  );
}
function Details({ ids, back }: { ids: number[]; back: () => void }) {
  const comparison = ids.length > 1;
  const url = comparison
    ? "/api/compare?" + ids.map((i) => `ids=${i}`).join("&")
    : `/api/providers/${ids[0]}`;
  const { data, error, loading } = useApi<Provider | Provider[]>(url);
  const rows = data ? (Array.isArray(data) ? data : [data]) : [];
  return (
    <>
      <button className="back" onClick={back}>
        <ArrowLeft size={16} /> Back to providers
      </button>
      <div className="heading">
        <div>
          <span className="eyebrow">EVIDENCE, NOT A BLACK BOX</span>
          <h1>{comparison ? "Provider comparison" : "Provider profile"}</h1>
          <p>Rankings apply only within the provider’s specialty.</p>
        </div>
      </div>
      {!data ? (
        <State error={error} loading={loading} />
      ) : (
        <>
          {comparison && <ComparisonChart providers={rows} />}
          <div className="compare-grid">
            {rows.map((p) => (
              <section className="panel profile" key={p.id}>
                <div className="avatar">{String(p.id).padStart(4, "0")}</div>
                <h2>{p.name}</h2>
                <p>
                  {p.specialty} · {p.location}
                </p>
                <ScoreBadge value={p.quality} />
                <p className="caption">
                  {p.rank === null ? "Not ranked" : `Specialty rank #${p.rank}`}{" "}
                  · {p.components.status}
                </p>
                <dl>
                  <dt>Encounters</dt>
                  <dd>{num(p.encounters)}</dd>
                  <dt>Observed outcomes</dt>
                  <dd>{num(p.observed)}</dd>
                  <dt>Mean encounter cost</dt>
                  <dd>{money(p.avg_cost)}</dd>
                  <dt>Outcome completeness</dt>
                  <dd>{(p.components.completeness * 100).toFixed(1)}%</dd>
                  <dt>Shrinkage weight</dt>
                  <dd>{p.components.shrinkage.toFixed(3)}</dd>
                  <dt>Outcome residual</dt>
                  <dd>{(p.components.residual * 100).toFixed(2)} pp</dd>
                  <dt>Normalized cost ratio</dt>
                  <dd>{p.components.cost_ratio.toFixed(3)}</dd>
                </dl>
                <h3>Score breakdown</h3>
                {(["outcome", "cost", "reliability", "volume"] as const).map(
                  (key, i) => (
                    <div className="component" key={key}>
                      <div>
                        <span>
                          {key} <small>· {[60, 25, 10, 5][i]}%</small>
                        </span>
                        <b>{p.components[key].toFixed(1)}</b>
                      </div>
                      <progress
                        aria-label={key + " component"}
                        max="100"
                        value={p.components[key]}
                      />
                    </div>
                  ),
                )}
              </section>
            ))}
          </div>
        </>
      )}
      <section className="panel method">
        <h2>How to read these scores</h2>
        <p>
          Expected success = 0.95 − 0.30 × synthetic risk. We average observed
          minus expected success and shrink toward neutral with n / (n + 50),
          where n is the observed outcome count. This is a known simulation
          baseline, not a learned clinical model.
        </p>
        <p>
          Costs are normalized for procedure and risk, then divided by the
          specialty mean. Fewer than 30 observed outcomes or completeness below
          80% means no score or rank. Reliability and volume describe evidence,
          not medical quality. Scores are not probabilities, confidence
          intervals, or causal estimates.
        </p>
      </section>
    </>
  );
}
function Explorer({ open }: { open: (ids: number[]) => void }) {
  const [q, setQ] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [location, setLocation] = useState("");
  const [quality, setQuality] = useState("");
  const [cost, setCost] = useState("");
  const [sort, setSort] = useState("quality");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Provider[]>([]);
  const [selectionError, setSelectionError] = useState("");
  const meta = useApi<Analytics>("/api/analytics");
  const params = new URLSearchParams({
    q,
    page: String(page),
    page_size: "12",
    sort,
  });
  if (specialty) params.set("specialty", specialty);
  if (location) params.set("location", location);
  if (quality) params.set("min_quality", quality);
  if (cost) params.set("max_cost", cost);
  const { data, error, loading } = useApi<ProviderPage>(
    "/api/providers?" + params,
  );
  function select(p: Provider) {
    setSelectionError("");
    if (selected.some((x) => x.id === p.id)) {
      setSelected(selected.filter((x) => x.id !== p.id));
      return;
    }
    if (selected.length && selected[0].specialty !== p.specialty) {
      setSelectionError("Choose providers in the same specialty.");
      return;
    }
    if (selected.length === 3) {
      setSelectionError("Compare up to three providers.");
      return;
    }
    setSelected([...selected, p]);
  }
  function change(setter: (s: string) => void, value: string) {
    setter(value);
    setPage(1);
  }
  return (
    <>
      <div className="heading">
        <div>
          <span className="eyebrow">PROVIDER EXPLORER</span>
          <h1>Find the signal in the data.</h1>
          <p>Select two or three providers in one specialty to compare.</p>
        </div>
        <button
          disabled={selected.length < 2}
          className="primary"
          onClick={() => open(selected.map((p) => p.id))}
        >
          <GitCompareArrows size={16} /> Compare ({selected.length})
        </button>
      </div>
      <section className="filters panel">
        <label className="search-field">
          Provider name
          <div>
            <Search size={17} />
            <input
              value={q}
              onChange={(e) => change(setQ, e.target.value)}
              placeholder="Search demo providers…"
            />
          </div>
        </label>
        <label>
          Specialty
          <select
            value={specialty}
            onChange={(e) => change(setSpecialty, e.target.value)}
          >
            <option value="">All specialties</option>
            {meta.data?.specialties.map((s) => (
              <option key={s.name}>{s.name}</option>
            ))}
          </select>
        </label>
        <label>
          Location
          <select
            value={location}
            onChange={(e) => change(setLocation, e.target.value)}
          >
            <option value="">All locations</option>
            {meta.data?.locations.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
        <label>
          Minimum score
          <input
            type="number"
            min="0"
            max="100"
            placeholder="Any"
            value={quality}
            onChange={(e) => change(setQuality, e.target.value)}
          />
        </label>
        <label>
          Maximum cost ($)
          <input
            type="number"
            min="1"
            placeholder="Any"
            value={cost}
            onChange={(e) => change(setCost, e.target.value)}
          />
        </label>
        <label>
          Sort by
          <select
            value={sort}
            onChange={(e) => change(setSort, e.target.value)}
          >
            <option value="quality">Quality score</option>
            <option value="cost">Lowest cost</option>
          </select>
        </label>
      </section>
      {selectionError && (
        <p role="alert" className="error">
          {selectionError}
        </p>
      )}
      {selected.length > 0 && (
        <div className="selection">
          Selected: {selected.map((p) => p.name).join(", ")}{" "}
          <button onClick={() => setSelected([])}>Clear</button>
        </div>
      )}
      <p className="caption">
        Scores are comparable within specialties only. Filter by specialty
        before interpreting order.
      </p>
      {!data ? (
        <State error={error} loading={loading} />
      ) : (
        <section className="panel table-panel">
          <div className="section-head">
            <h2>
              Providers <span className="count">{num(data.total)}</span>
            </h2>
            <span className="caption">Synthetic cohort · demo-v1</span>
          </div>
          {data.items.length === 0 ? (
            <div className="state">No providers match these filters.</div>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Select</th>
                    <th>Provider</th>
                    <th>Specialty</th>
                    <th>Location</th>
                    <th>Encounters</th>
                    <th>Mean cost</th>
                    <th>Demo score</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((p) => (
                    <tr key={p.id}>
                      <td>
                        <input
                          type="checkbox"
                          aria-label={`Compare ${p.name}`}
                          checked={selected.some((x) => x.id === p.id)}
                          onChange={() => select(p)}
                        />
                      </td>
                      <td>
                        <button
                          className="provider-link"
                          onClick={() => open([p.id])}
                        >
                          {p.name}
                          <ArrowUpRight size={14} />
                        </button>
                        <small className="provider-sub">
                          {p.rank
                            ? `Specialty rank #${p.rank}`
                            : "Insufficient evidence"}
                        </small>
                      </td>
                      <td>{p.specialty}</td>
                      <td>{p.location}</td>
                      <td>{num(p.encounters)}</td>
                      <td>{money(p.avg_cost)}</td>
                      <td>
                        <ScoreBadge value={p.quality} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="pagination">
            <span>
              Page {page} of {Math.max(1, Math.ceil(data.total / 12))}
            </span>
            <div>
              <button disabled={page === 1} onClick={() => setPage(page - 1)}>
                Previous
              </button>
              <button
                disabled={page * 12 >= data.total}
                onClick={() => setPage(page + 1)}
              >
                Next
              </button>
            </div>
          </div>
        </section>
      )}
    </>
  );
}
export default function App() {
  const [page, setPage] = useState<
    | "overview"
    | "analytics"
    | "providers"
    | "details"
    | "dataops"
    | "operations"
    | "reliability"
  >("overview");
  const [ids, setIds] = useState<number[]>([]);
  const [inspection, setInspection] = useState<
    | { runId: string; snapshotId: string | null; mode: "cms" | "fixture" }
    | undefined
  >();
  return (
    <div className="app">
      <aside>
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setPage("overview");
          }}
        >
          <div className="brand-icon">
            <Activity />
          </div>
          CareRank <span>LAB</span>
        </a>
        <div className="workspace-label">RESEARCH WORKSPACE</div>
        <nav aria-label="Main navigation">
          <button
            aria-current={page === "overview" ? "page" : undefined}
            onClick={() => setPage("overview")}
          >
            <BarChart3 size={19} /> Overview
          </button>
          <button
            aria-current={
              page === "providers" || page === "details" ? "page" : undefined
            }
            onClick={() => setPage("providers")}
          >
            <Users size={19} /> Provider explorer
          </button>
          <button
            aria-current={page === "analytics" ? "page" : undefined}
            onClick={() => setPage("analytics")}
          >
            <Activity size={19} /> Analytics
          </button>
          <button
            aria-current={page === "dataops" ? "page" : undefined}
            onClick={() => setPage("dataops")}
          >
            <Database size={19} /> Data operations
          </button>
          <button
            aria-current={page === "operations" ? "page" : undefined}
            onClick={() => setPage("operations")}
          >
            <Activity size={19} /> Pipeline operations
          </button>
          <button
            aria-current={page === "reliability" ? "page" : undefined}
            onClick={() => setPage("reliability")}
          >
            <ShieldCheck size={19} /> Reliability
          </button>
        </nav>
        <div className="sidebar-note">
          <FlaskConical />
          <h3>Built for curiosity.</h3>
          <p>A transparent playground for healthcare analytics.</p>
          <small>Independent portfolio project</small>
        </div>
        <div className="sidebar-bottom">
          <div className="user-avatar">PM</div>
          <div>
            Prabhat Mattaparthi<small>CareRank Lab workspace</small>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header>
          <div>
            Workspace <span>/</span>{" "}
            <b>
              {page === "overview"
                ? "Overview"
                : page === "providers"
                  ? "Providers"
                  : page === "analytics"
                    ? "Analytics"
                    : page === "dataops"
                      ? "Data operations"
                      : page === "operations"
                        ? "Pipeline operations"
                        : page === "reliability"
                          ? "Operational reliability"
                          : "Provider evidence"}
            </b>
          </div>
          <span className="pill">
            {page === "dataops" ||
            page === "operations" ||
            page === "reliability"
              ? "● Public registry / fixture workspace"
              : "● Synthetic environment"}
          </span>
        </header>
        <div className="disclaimer">
          <ShieldCheck size={16} />
          <span>
            {page === "dataops" ||
            page === "operations" ||
            page === "reliability" ? (
              <>
                Public registry and labeled test fixtures. No patient data or
                clinical ratings. Not affiliated with Garner.
              </>
            ) : (
              <>
                <strong>Demonstration only.</strong> All data and scores are
                synthetic. Not suitable for healthcare decisions. Not affiliated
                with Garner.
              </>
            )}
          </span>
        </div>
        <main>
          {page === "overview" ? (
            <Overview
              open={() => setPage("providers")}
              analyze={() => setPage("analytics")}
            />
          ) : page === "dataops" ? (
            <DataOps
              key={inspection?.runId || "default"}
              initialInspection={inspection}
            />
          ) : page === "operations" ? (
            <PipelineOperations
              onEvidence={(runId, snapshotId, mode) => {
                setInspection({ runId, snapshotId, mode });
                setPage("dataops");
              }}
            />
          ) : page === "reliability" ? (
            <Reliability
              onPipelines={() => setPage("operations")}
              onDataOperations={() => {
                setInspection(undefined);
                setPage("dataops");
              }}
            />
          ) : page === "analytics" ? (
            <AnalyticsPage
              open={(next) => {
                setIds(next);
                setPage("details");
              }}
            />
          ) : page === "providers" ? (
            <Explorer
              open={(next) => {
                setIds(next);
                setPage("details");
              }}
            />
          ) : (
            <Details ids={ids} back={() => setPage("providers")} />
          )}
        </main>
        <footer>
          CareRank Lab{" "}
          <span>
            {page === "dataops" ||
            page === "operations" ||
            page === "reliability"
              ? "Public provenance. Separate test fixtures. No clinical scores."
              : "Transparent methods. Fictional data. Real engineering practice."}
          </span>
        </footer>
      </div>
    </div>
  );
}
