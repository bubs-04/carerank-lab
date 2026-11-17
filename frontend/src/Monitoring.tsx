import { useState } from "react";
import { useApi } from "./api";
import { useAuth } from "./Auth";
import IncidentActions from "./IncidentActions";

type Page<T> = { items: T[]; total: number; page: number; page_size: number };
type Run = {
  id: string;
  status: string;
  started_at: string;
  snapshot_id: string | null;
  received: number | null;
  requested: number;
  error_code: string | null;
};
type Summary = {
  health: string;
  explanation: string;
  profile: string;
  expected_rules: number;
  latest_run: Run | null;
  evaluations: Record<string, number>;
  open_by_severity: Record<string, number>;
  caveat: string;
};
type Evaluation = {
  id: string;
  run_id: string;
  snapshot_id: string | null;
  baseline_run_id: string | null;
  profile: string;
  observed: number | null;
  status: string;
  explanation: string;
  evidence: Record<string, unknown>;
  rule: {
    rule_id: string;
    version: string;
    id: string;
    threshold: number;
    unit: string;
    description: string;
    severity: string;
  };
};
type Alert = {
  id: string;
  run_id: string;
  severity: string;
  status: string;
  assigned_to: string | null;
  assigned_user_id?: string | null;
  resolution: string | null;
  revision: number;
  created_at: string;
};
type Event = {
  id: string;
  revision: number;
  actor: string;
  actor_user_id?: string | null;
  previous_assigned_to?: string | null;
  action: string;
  from_status: string | null;
  to_status: string;
  assigned_to: string | null;
  note: string;
  created_at: string;
};
type Trend = {
  scope: { max_rows?: number } | null;
  policy: string | null;
  caveat: string;
  points: {
    run_id: string;
    started_at: string;
    received: number;
    valid: number;
    rejected: number;
    warnings: number;
  }[];
};
type Inspect = (runId: string, snapshotId?: string | null) => void;
const base = "/api/dataops/monitoring";
const short = (id: string) => id.slice(0, 8);
const label = (value: string) => value.replaceAll("_", " ");
function Loading({ error }: { error: string }) {
  return (
    <p role={error ? "alert" : "status"}>
      {error
        ? `Monitoring unavailable: ${error}. Check migration 003 and use Refresh status to retry.`
        : "Loading monitoring evidence…"}
    </p>
  );
}
function Pager({
  page,
  total,
  setPage,
}: {
  page: number;
  total: number;
  setPage: (p: number) => void;
}) {
  return (
    <div className="pagination">
      <span>
        Page {page} of {Math.max(1, Math.ceil(total / 20))} · {total} results
      </span>
      <div>
        <button onClick={() => setPage(page - 1)} disabled={page === 1}>
          Previous
        </button>
        <button onClick={() => setPage(page + 1)} disabled={page * 20 >= total}>
          Next
        </button>
      </div>
    </div>
  );
}
function Bars({
  counts,
  title,
}: {
  counts: Record<string, number>;
  title: string;
}) {
  const max = Math.max(1, ...Object.values(counts));
  return (
    <div role="group" aria-label={title} className="bars">
      {Object.entries(counts).map(([name, count]) => (
        <div className="bar-row" key={name}>
          <span>{label(name)}</span>
          <div className="bar-track" title={`${label(name)}: ${count}`}>
            <div style={{ width: `${(100 * count) / max}%` }} />
          </div>
          <b>{count}</b>
        </div>
      ))}
    </div>
  );
}
function Evidence({
  evaluation: e,
  onInspect,
}: {
  evaluation: Evaluation;
  onInspect: Inspect;
}) {
  return (
    <div className="monitor-evidence">
      <p>
        <strong>{e.rule.description}</strong>
      </p>
      <p>{e.explanation}</p>
      <p>
        Observed: {e.observed === null ? "Unavailable" : e.observed.toFixed(2)}{" "}
        {e.observed === null ? "" : e.rule.unit} · Alert threshold: &gt;{" "}
        {e.rule.threshold} {e.rule.unit} · Severity: {e.rule.severity}
      </p>
      <p>
        Rule {e.rule.rule_id} · algorithm {e.rule.version} · config{" "}
        {short(e.rule.id)} · result: <strong>{label(e.status)}</strong>
      </p>
      <div className="dataops-actions">
        <button onClick={() => onInspect(e.run_id)}>
          View attempt and findings
        </button>
        {e.snapshot_id && (
          <button onClick={() => onInspect(e.run_id, e.snapshot_id)}>
            View snapshot records
          </button>
        )}
        {e.baseline_run_id && (
          <button onClick={() => onInspect(e.baseline_run_id!)}>
            View baseline findings
          </button>
        )}
      </div>
      <details>
        <summary>Reproducible evidence and configuration</summary>
        <pre className="dataops-code">
          {JSON.stringify(
            { profile: e.profile, rule: e.rule, ...e.evidence },
            null,
            2,
          )}
        </pre>
      </details>
    </div>
  );
}
function AlertInvestigation({
  id,
  onInspect,
  onUpdated,
}: {
  id: string;
  onInspect: Inspect;
  onUpdated: () => void;
}) {
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const [notice, setNotice] = useState("");
  const detail = useApi<{ alert: Alert; evaluation: Evaluation }>(
    `${base}/alerts/${encodeURIComponent(id)}`,
    refresh,
  );
  const events = useApi<Page<Event>>(
    `${base}/alerts/${encodeURIComponent(id)}/events?page=${page}`,
    refresh,
  );
  if (!detail.data) return <Loading error={detail.error} />;
  const { alert, evaluation } = detail.data;
  return (
    <section className="panel" aria-label="Alert investigation">
      <h2>Investigation · {short(id)}</h2>
      <p>
        {alert.severity} · {alert.status} · revision {alert.revision} · Assigned
        to: {alert.assigned_to || "Unassigned"}
      </p>
      {alert.resolution && <p>Resolution: {alert.resolution}</p>}
      {notice && (
        <p className="save-notice" role="status">
          {notice}
        </p>
      )}
      <IncidentActions
        key={alert.revision}
        incident={alert}
        onSaved={() => {
          setNotice(
            "Decision saved. The incident and audit history are up to date.",
          );
          setPage(1);
          setRefresh((n) => n + 1);
          onUpdated();
        }}
        onReload={() => {
          setNotice("");
          setRefresh((n) => n + 1);
          onUpdated();
        }}
      />
      <Evidence evaluation={evaluation} onInspect={onInspect} />
      <h3>Append-only investigation history</h3>
      <p>
        Web decisions are attributed to the signed-in account. Historical CLI
        events retain their original operator labels.
      </p>
      {!events.data ? (
        <Loading error={events.error} />
      ) : (
        <>
          <ol className="monitor-timeline">
            {events.data.items.map((e) => (
              <li key={e.id}>
                <strong>
                  Revision {e.revision}: {e.from_status || "created"} →{" "}
                  {e.to_status}
                </strong>
                <p>{e.note}</p>
                <small>
                  {e.actor} ·{" "}
                  {e.actor_user_id
                    ? "Authenticated account"
                    : "System / legacy CLI"}{" "}
                  · {new Date(e.created_at).toLocaleString()} · Assigned:{" "}
                  {e.assigned_to || "Unassigned"}
                  {e.previous_assigned_to &&
                    ` · Previous owner: ${e.previous_assigned_to}`}
                </small>
              </li>
            ))}
          </ol>
          <Pager page={page} total={events.data.total} setPage={setPage} />
        </>
      )}
      <details>
        <summary>Investigate using the local CLI</summary>
        <p>
          Read the evidence first. Copy the command into Terminal inside the
          project. Change the note and actor to your own words. Use the next
          revision after each update.
        </p>
        <pre className="dataops-code">{`docker compose run --rm --no-deps api python -m app.monitoring inspect ${id}\n\ndocker compose run --rm --no-deps api python -m app.monitoring investigate ${id} --actor "YOUR_NAME" --expected-revision ${alert.revision} --note "Describe what you checked"`}</pre>
        <p>
          This command records a note. Add an allowed --status transition to
          change status. CLI operations require trusted server access; use the
          authenticated form above for account-attributed decisions.
        </p>
      </details>
    </section>
  );
}
function Trends({ mode, runId }: { mode: string; runId: string }) {
  const result = useApi<Trend>(
    `${base}/trends?mode=${mode}${runId ? `&run_id=${encodeURIComponent(runId)}` : ""}`,
  );
  if (!result.data) return <Loading error={result.error} />;
  const { points, scope, policy } = result.data;
  if (!points.length)
    return (
      <p>
        No comparable successful retrievals yet. Failed attempts remain in
        ingestion history.
      </p>
    );
  const max = Math.max(1, ...points.map((p) => p.valid));
  const path = points
    .map(
      (p, i) =>
        `${20 + (i * 560) / Math.max(1, points.length - 1)},${150 - (120 * p.valid) / max}`,
    )
    .join(" ");
  return (
    <>
      <p>
        Up to 20 successful retrievals with the same source, prefix size (
        {scope?.max_rows ?? "unknown"}) and policy ({policy}). Version reuse is
        retained as an attempt. Failed attempts are shown in ingestion history.
      </p>
      {points.length < 2 ? (
        <p>Only one comparable retrieval; no trend can be inferred.</p>
      ) : (
        <svg
          className="monitor-trend"
          viewBox="0 0 620 190"
          role="img"
          aria-label="Accepted record counts across comparable successful retrievals; exact values in the table below"
        >
          <title>
            Accepted records in retrieval order; vertical axis starts at zero
          </title>
          <path d="M20 25 V150 H590" fill="none" stroke="currentColor" />
          <text x="4" y="170">
            0
          </text>
          <text x="25" y="20">
            {max} accepted rows
          </text>
          <polyline
            points={path}
            fill="none"
            stroke="#167a70"
            strokeWidth="3"
          />
          {points.map((p, i) => (
            <circle
              key={p.run_id}
              cx={20 + (i * 560) / Math.max(1, points.length - 1)}
              cy={150 - (120 * p.valid) / max}
              r="4"
              fill="#167a70"
            >
              <title>
                {short(p.run_id)}: {p.valid} accepted records
              </title>
            </circle>
          ))}
          <text x="20" y="185">
            Earlier retrieval
          </text>
          <text x="455" y="185">
            Latest retrieval
          </text>
        </svg>
      )}
      <div className="table-scroll">
        <table>
          <caption>Comparable retrieval counts (exact chart values)</caption>
          <thead>
            <tr>
              <th>Run / time</th>
              <th>Accepted</th>
              <th>Rejected</th>
              <th>Warning findings</th>
            </tr>
          </thead>
          <tbody>
            {points.map((p) => (
              <tr key={p.run_id}>
                <td>
                  {short(p.run_id)} · {new Date(p.started_at).toLocaleString()}
                </td>
                <td>{p.valid}</td>
                <td>
                  {p.rejected} / {p.received}
                </td>
                <td>{p.warnings}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="caption">{result.data.caveat}</p>
    </>
  );
}
export default function Monitoring({
  mode,
  onInspect,
}: {
  mode: "cms" | "fixture";
  onInspect: Inspect;
}) {
  const auth = useAuth();
  const [refresh, setRefresh] = useState(0);
  const [assignment, setAssignment] = useState("");
  const [alertPage, setAlertPage] = useState(1),
    [evalPage, setEvalPage] = useState(1);
  const [status, setStatus] = useState(""),
    [severity, setSeverity] = useState("");
  const [selectedAlert, setSelectedAlert] = useState(""),
    [runId, setRunId] = useState("");
  const [historical, setHistorical] = useState(false),
    [trendRun, setTrendRun] = useState("");
  const summary = useApi<Summary>(`${base}/summary?mode=${mode}`, refresh);
  const alerts = useApi<Page<Alert>>(
    `${base}/alerts?mode=${mode}&page=${alertPage}${status ? `&status=${status}` : ""}${severity ? `&severity=${severity}` : ""}${assignment ? `&assigned_to=${assignment}` : ""}`,
    refresh,
  );
  const evaluations = useApi<Page<Evaluation>>(
    `${base}/evaluations?mode=${mode}&page=${evalPage}&current_only=${!historical}${runId ? `&run_id=${encodeURIComponent(runId)}` : ""}`,
  );
  const runs = useApi<Page<Run>>(`/api/dataops/runs?mode=${mode}&page_size=50`);
  return (
    <div className="monitoring">
      <section className="panel">
        <span className="eyebrow">
          REGISTRY RELIABILITY · ANALYST WORKSPACE
        </span>
        <h2>Data quality monitoring</h2>
        {!summary.data ? (
          <Loading error={summary.error} />
        ) : (
          <>
            <div
              className={`monitor-health monitor-${summary.data.health}`}
              role="status"
            >
              <strong>{label(summary.data.health)}</strong>
              <p>{summary.data.explanation}</p>
            </div>
            <p>
              Current profile {short(summary.data.profile)} ·{" "}
              {summary.data.expected_rules} rules · Latest attempt{" "}
              {summary.data.latest_run
                ? `${short(summary.data.latest_run.id)} (${summary.data.latest_run.status})`
                : "none"}
            </p>
            <div className="monitor-columns">
              <div>
                <h3>Latest attempt evaluations</h3>
                <Bars
                  title="Latest rule evaluation outcomes"
                  counts={{
                    passed: summary.data.evaluations.passed || 0,
                    failed: summary.data.evaluations.failed || 0,
                    not_evaluable: summary.data.evaluations.not_evaluable || 0,
                  }}
                />
              </div>
              <div>
                <h3>Unresolved alerts across history</h3>
                <Bars
                  title="Unresolved alerts by severity"
                  counts={{
                    critical: summary.data.open_by_severity.critical || 0,
                    warning: summary.data.open_by_severity.warning || 0,
                  }}
                />
              </div>
            </div>
            <p>{summary.data.caveat}</p>
            {summary.data.latest_run && (
              <button
                onClick={() => {
                  setRunId(summary.data!.latest_run!.id);
                  setEvalPage(1);
                }}
              >
                Show latest attempt evaluations
              </button>
            )}
          </>
        )}
        <details>
          <summary>Evaluate existing history</summary>
          <pre className="dataops-code">{`docker compose run --rm --no-deps api python -m app.monitoring evaluate --mode ${mode} --limit 100`}</pre>
          <p>
            New completed ingestions evaluate automatically. Backfill older
            attempts with this bounded command; repeat until evaluated_attempts
            is zero. Refresh status afterward.
          </p>
        </details>
      </section>
      <section className="panel">
        <div className="queue-heading">
          <div>
            <span className="eyebrow">INVESTIGATION QUEUE</span>
            <h2>Alert history</h2>
            <p>
              Prioritize findings, coordinate ownership, and keep decisions
              traceable.
            </p>
          </div>
          <span className="role-label">
            {auth?.user.role || "viewer"} access
          </span>
        </div>
        <div className="dataops-actions">
          <label>
            Alert status
            <select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setAlertPage(1);
              }}
            >
              <option value="">All statuses</option>
              {["open", "acknowledged", "investigating", "resolved"].map(
                (s) => (
                  <option key={s}>{s}</option>
                ),
              )}
            </select>
          </label>
          <label>
            Assignment
            <select
              value={assignment}
              onChange={(e) => {
                setAssignment(e.target.value);
                setAlertPage(1);
              }}
            >
              <option value="">All assignments</option>
              {auth && <option value="me">Assigned to me</option>}
              <option value="unassigned">Unassigned</option>
            </select>
          </label>
          <label>
            Alert severity
            <select
              value={severity}
              onChange={(e) => {
                setSeverity(e.target.value);
                setAlertPage(1);
              }}
            >
              <option value="">All severities</option>
              <option>critical</option>
              <option>warning</option>
            </select>
          </label>
        </div>
        {!alerts.data ? (
          <Loading error={alerts.error} />
        ) : (
          <>
            {!alerts.data.total ? (
              <p>
                No alerts match these filters. This does not establish that
                monitoring passed; check rule coverage above.
              </p>
            ) : (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Alert / created</th>
                      <th>Severity / state</th>
                      <th>Owner</th>
                      <th>Attempt</th>
                      <th>Investigation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {alerts.data.items.map((a) => (
                      <tr key={a.id}>
                        <td>
                          {short(a.id)}
                          <br />
                          {new Date(a.created_at).toLocaleString()}
                        </td>
                        <td>
                          <span className={`severity severity-${a.severity}`}>
                            {a.severity}
                          </span>
                          <span
                            className={`incident-status status-${a.status}`}
                          >
                            {label(a.status)}
                          </span>
                        </td>
                        <td>
                          {a.assigned_to || (
                            <span className="unassigned">Unassigned</span>
                          )}
                        </td>
                        <td>{short(a.run_id)}</td>
                        <td>
                          <button
                            aria-label={`Inspect alert ${short(a.id)}`}
                            onClick={() => setSelectedAlert(a.id)}
                          >
                            Inspect evidence
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <Pager
              page={alertPage}
              total={alerts.data.total}
              setPage={setAlertPage}
            />
          </>
        )}
      </section>
      {selectedAlert && (
        <AlertInvestigation
          key={selectedAlert}
          id={selectedAlert}
          onInspect={onInspect}
          onUpdated={() => setRefresh((n) => n + 1)}
        />
      )}
      <section className="panel">
        <h2>Rule evaluation results</h2>
        <div className="dataops-actions">
          <label>
            Evaluation attempt
            <select
              value={runId}
              onChange={(e) => {
                setRunId(e.target.value);
                setEvalPage(1);
              }}
            >
              <option value="">All attempts</option>
              {runId && !runs.data?.items.some((r) => r.id === runId) && (
                <option value={runId}>{short(runId)}</option>
              )}
              {runs.data?.items.map((r) => (
                <option key={r.id} value={r.id}>
                  {short(r.id)} · {r.status}
                </option>
              ))}
            </select>
          </label>
          <label>
            <input
              type="checkbox"
              checked={historical}
              onChange={(e) => {
                setHistorical(e.target.checked);
                setEvalPage(1);
              }}
            />{" "}
            Include historical rule configurations
          </label>
        </div>
        {runs.error && <Loading error={runs.error} />}
        {!evaluations.data ? (
          <Loading error={evaluations.error} />
        ) : (
          <>
            {!evaluations.data.total ? (
              <p>
                No matching evaluations. Run the CLI backfill; absence of
                results is not a pass.
              </p>
            ) : (
              evaluations.data.items.map((e) => (
                <details className="monitor-rule" key={e.id}>
                  <summary>
                    {e.rule.rule_id} · {label(e.status)} · run {short(e.run_id)}{" "}
                    ·{" "}
                    {e.observed === null
                      ? "Unavailable"
                      : e.observed.toFixed(2)}{" "}
                    {e.observed === null ? "" : e.rule.unit}
                  </summary>
                  <Evidence evaluation={e} onInspect={onInspect} />
                </details>
              ))
            )}
            <Pager
              page={evalPage}
              total={evaluations.data.total}
              setPage={setEvalPage}
            />
          </>
        )}
      </section>
      <section className="panel">
        <h2>Comparable retrieval trends</h2>
        <label>
          Trend reference attempt
          <select
            value={trendRun}
            onChange={(e) => setTrendRun(e.target.value)}
          >
            <option value="">Latest successful attempt</option>
            {runs.data?.items
              .filter((r) => ["succeeded", "no_change"].includes(r.status))
              .map((r) => (
                <option value={r.id} key={r.id}>
                  {short(r.id)}
                </option>
              ))}
          </select>
        </label>
        <Trends mode={mode} runId={trendRun} />
      </section>
    </div>
  );
}
