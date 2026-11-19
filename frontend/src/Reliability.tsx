import { useEffect, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  Clock3,
  Database,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { useApi } from "./api";

export type ReliabilityReport = {
  window: { hours: number; from: string; to: string };
  workers: {
    worker_id: string;
    instance_id: string;
    state: string;
    started_at: string;
    heartbeat_at: string;
    execution_id: string | null;
    healthy: boolean;
    age_seconds: number;
  }[];
  summary: {
    completed: number;
    succeeded: number;
    failed: number;
    cancelled: number;
    retried_executions: number;
    retry_attempts: number;
    success_rate: number | null;
    p50_duration_seconds: number | null;
    p95_duration_seconds: number | null;
  };
  queue: {
    queued: number;
    running: number;
    retry_wait: number;
    overdue_leases: number;
    oldest_ready_age_seconds: number | null;
  };
  activity: {
    hour: string;
    completed: number;
    succeeded: number;
    failed: number;
    retries: number;
  }[];
  quality: { open_alerts: number; critical_open_alerts: number };
  limits: { heartbeat_stale_seconds: number; max_window_hours: number };
  generated_at: string;
};

const count = (value: number) => value.toLocaleString();
const date = (value: string) => new Date(value).toLocaleString();
const elapsed = (value: number | null) => {
  if (value === null) return "No sample";
  if (value < 60) return `${value.toFixed(1)}s`;
  if (value < 3600) return `${(value / 60).toFixed(1)}m`;
  return `${(value / 3600).toFixed(1)}h`;
};

function ActivityChart({ report }: { report: ReliabilityReport }) {
  const hour = 3600000;
  const start = Math.floor(Date.parse(report.window.from) / hour) * hour;
  const finish = Math.floor(Date.parse(report.window.to) / hour) * hour;
  const actual = new Map(
    report.activity.map((item) => [Date.parse(item.hour), item]),
  );
  const buckets = Array.from(
    { length: Math.max(1, Math.round((finish - start) / hour) + 1) },
    (_, index) => {
      const timestamp = start + index * hour;
      return (
        actual.get(timestamp) || {
          hour: new Date(timestamp).toISOString(),
          completed: 0,
          succeeded: 0,
          failed: 0,
          retries: 0,
        }
      );
    },
  );
  const max = Math.max(
    1,
    ...buckets.map((item) => Math.max(item.completed, item.retries)),
  );
  const width = 840;
  const baseline = 158;
  const step = width / buckets.length;
  const scale = 130 / max;
  return (
    <>
      <div className="reliability-legend" aria-label="Activity chart legend">
        <span>
          <i className="reliability-succeeded" />
          Succeeded
        </span>
        <span>
          <i className="reliability-failed" />
          Failed / timed out
        </span>
        <span>
          <i className="reliability-cancelled" />
          Cancelled
        </span>
        <span>
          <i className="reliability-retried" />
          Retry attempts started
        </span>
      </div>
      <svg
        className="reliability-chart"
        viewBox="0 0 840 180"
        role="img"
        aria-label={`Hourly pipeline activity over the last ${report.window.hours} hours; exact counts are available below`}
      >
        <line x1="0" y1={baseline} x2={width} y2={baseline} stroke="#bdceca" />
        <text x="0" y="14" fill="#607775" fontSize="12">
          {count(max)} per hour
        </text>
        {buckets.map((item, index) => {
          const x = index * step + step * 0.12;
          const barWidth = step * 0.76;
          const cancelled = Math.max(
            0,
            item.completed - item.succeeded - item.failed,
          );
          return (
            <g key={item.hour}>
              <title>
                {date(item.hour)}: {item.succeeded} succeeded, {item.failed}{" "}
                failed or timed out, {cancelled} cancelled, {item.retries} retry
                attempts
              </title>
              <rect
                x={x}
                y={baseline - item.succeeded * scale}
                width={barWidth}
                height={item.succeeded * scale}
                fill="#348469"
              />
              <rect
                x={x}
                y={baseline - (item.succeeded + item.failed) * scale}
                width={barWidth}
                height={item.failed * scale}
                fill="#b34b47"
              />
              <rect
                x={x}
                y={baseline - item.completed * scale}
                width={barWidth}
                height={cancelled * scale}
                fill="#9badb1"
              />
              {item.retries > 0 && (
                <circle
                  cx={x + barWidth / 2}
                  cy={baseline - item.retries * scale}
                  r={Math.min(4, step * 0.28)}
                  fill="#ae741f"
                  stroke="white"
                  strokeWidth="1"
                />
              )}
            </g>
          );
        })}
      </svg>
      <div className="reliability-chart-range">
        <time dateTime={report.window.from}>{date(report.window.from)}</time>
        <time dateTime={report.window.to}>{date(report.window.to)}</time>
      </div>
      <details className="reliability-exact">
        <summary>Exact hourly activity</summary>
        {report.activity.length ? (
          <div className="table-scroll">
            <table>
              <caption>
                Hours with recorded activity; other hours have zero events. The
                first and last hour may be partial.
              </caption>
              <thead>
                <tr>
                  <th>Hour</th>
                  <th>Completed</th>
                  <th>Succeeded</th>
                  <th>Failed / timed out</th>
                  <th>Retry attempts</th>
                </tr>
              </thead>
              <tbody>
                {report.activity.map((item) => (
                  <tr key={item.hour}>
                    <td>{date(item.hour)}</td>
                    <td>{count(item.completed)}</td>
                    <td>{count(item.succeeded)}</td>
                    <td>{count(item.failed)}</td>
                    <td>{count(item.retries)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p>
            No execution completions or retry starts recorded in this window.
          </p>
        )}
      </details>
    </>
  );
}

export default function Reliability({
  onPipelines,
  onDataOperations,
}: {
  onPipelines: () => void;
  onDataOperations: () => void;
}) {
  const [hours, setHours] = useState(24);
  const [refresh, setRefresh] = useState(0);
  const [automatic, setAutomatic] = useState(true);
  const response = useApi<ReliabilityReport>(
    `/api/operations/reliability?hours=${hours}`,
    refresh,
  );
  const [retained, setRetained] = useState<ReliabilityReport | null>(null);
  const current = response.data?.window.hours === hours ? response.data : null;
  const report =
    current || (retained?.window.hours === hours ? retained : null);
  useEffect(() => {
    if (current) setRetained(current);
  }, [current]);
  useEffect(() => {
    if (!automatic) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "hidden")
        setRefresh((value) => value + 1);
    }, 15000);
    return () => window.clearInterval(timer);
  }, [automatic]);
  const healthy =
    report?.workers.filter((worker) => worker.healthy).length || 0;
  return (
    <div className="reliability-workspace">
      <div className="heading">
        <div>
          <span className="eyebrow">PLATFORM · RELIABILITY</span>
          <h1>Operational reliability</h1>
          <p>
            Measured execution outcomes, worker presence, and evidence for the
            next decision.
          </p>
        </div>
        <button
          onClick={() => setRefresh((value) => value + 1)}
          disabled={response.loading}
        >
          <RefreshCw size={16} />
          Refresh reliability
        </button>
      </div>
      <div className="reliability-controls">
        <label>
          Observation window
          <select
            value={hours}
            onChange={(event) => setHours(Number(event.target.value))}
          >
            <option value={1}>Last hour</option>
            <option value={24}>Last 24 hours</option>
            <option value={168}>Last 7 days</option>
          </select>
        </label>
        <label className="reliability-check">
          <input
            type="checkbox"
            checked={automatic}
            onChange={(event) => setAutomatic(event.target.checked)}
          />
          Refresh every 15 seconds
        </label>
        <span className="reliability-readonly">
          <ShieldCheck size={15} />
          Authenticated, read-only evidence
        </span>
      </div>
      {response.error && (
        <div className="reliability-error" role="alert">
          <strong>Reliability data could not refresh.</strong>
          <p>{response.error}</p>
          {report && (
            <p>
              Showing the last successful response from{" "}
              {date(report.generated_at)}. Worker states may now be stale.
            </p>
          )}
        </div>
      )}
      {!report ? (
        <div className="panel" role="status">
          {response.error
            ? "No reliability evidence is available for this window. Use Refresh reliability to try again."
            : "Loading operational evidence…"}
        </div>
      ) : (
        <>
          <div
            className={`reliability-health ${response.error || healthy === 0 || report.queue.overdue_leases > 0 ? "reliability-attention" : ""}`}
          >
            <Activity size={24} aria-hidden="true" />
            <div>
              <strong>
                {response.error
                  ? "Last recorded operational state"
                  : healthy
                    ? `${healthy} worker${healthy === 1 ? "" : "s"} reporting a recent heartbeat`
                    : "No healthy worker heartbeat recorded"}
              </strong>
              <p>
                {report.queue.overdue_leases > 0
                  ? `${count(report.queue.overdue_leases)} running execution(s) have an expired lease or deadline. A worker must recover them.`
                  : "Queue and worker state are current at the sample time; they are not an uptime guarantee."}
              </p>
            </div>
            <time dateTime={report.generated_at}>
              Sampled {date(report.generated_at)}
            </time>
          </div>
          <div
            className="reliability-metrics"
            aria-label="Execution reliability metrics"
          >
            <article>
              <span>Success rate</span>
              <strong>
                {report.summary.success_rate === null
                  ? "No sample"
                  : `${(report.summary.success_rate * 100).toFixed(1)}%`}
              </strong>
              <small>
                {count(report.summary.succeeded)} succeeded /{" "}
                {count(report.summary.succeeded + report.summary.failed)}{" "}
                non-cancelled outcomes
              </small>
            </article>
            <article>
              <span>Completed executions</span>
              <strong>{count(report.summary.completed)}</strong>
              <small>
                {count(report.summary.failed)} failed or timed out ·{" "}
                {count(report.summary.cancelled)} cancelled
              </small>
            </article>
            <article>
              <span>Retry attempts started</span>
              <strong>{count(report.summary.retry_attempts)}</strong>
              <small>
                {count(report.summary.retried_executions)} completed
                execution(s) required multiple attempts
              </small>
            </article>
            <article>
              <span>P95 execution duration</span>
              <strong>{elapsed(report.summary.p95_duration_seconds)}</strong>
              <small>P50 {elapsed(report.summary.p50_duration_seconds)}</small>
            </article>
          </div>
          <p className="reliability-scope">
            Outcomes use executions finished in the selected window. Success
            excludes cancellations and counts exhausted timeouts as failures.
            Durations run from first start to finish, include retry backoff, and
            exclude work cancelled before it started. Retry counts use attempt
            start times. These are observed samples, not a service-level
            objective.
          </p>
          <section className="panel">
            <div className="queue-heading">
              <div>
                <span className="eyebrow">OUTCOMES OVER TIME</span>
                <h2>Execution and recovery activity</h2>
              </div>
              <Activity aria-hidden="true" size={22} />
            </div>
            <ActivityChart report={report} />
          </section>
          <div className="reliability-columns">
            <section className="panel">
              <div className="queue-heading">
                <div>
                  <span className="eyebrow">CURRENT STATE · ALL HISTORY</span>
                  <h2>Work waiting for progress</h2>
                </div>
                <Clock3 aria-hidden="true" size={22} />
              </div>
              <dl className="reliability-queue">
                <div>
                  <dt>Queued</dt>
                  <dd>{count(report.queue.queued)}</dd>
                </div>
                <div>
                  <dt>Running</dt>
                  <dd>{count(report.queue.running)}</dd>
                </div>
                <div>
                  <dt>Waiting to retry</dt>
                  <dd>{count(report.queue.retry_wait)}</dd>
                </div>
                <div>
                  <dt>Expired lease / deadline</dt>
                  <dd>{count(report.queue.overdue_leases)}</dd>
                </div>
              </dl>
              <p>
                Oldest due queued or retry work:{" "}
                <strong>
                  {report.queue.oldest_ready_age_seconds === null
                    ? "None due"
                    : elapsed(report.queue.oldest_ready_age_seconds)}
                </strong>
                . Includes blocked work whose scheduled time has arrived; it may
                not be claimable yet. Future retry delays are excluded.
              </p>
              <button onClick={onPipelines}>
                Inspect pipeline histories <ArrowUpRight size={15} />
              </button>
            </section>
            <section className="panel">
              <div className="queue-heading">
                <div>
                  <span className="eyebrow">
                    QUALITY · ALL UNRESOLVED ALERTS
                  </span>
                  <h2>Evidence needing investigation</h2>
                </div>
                <ShieldCheck aria-hidden="true" size={22} />
              </div>
              <div className="reliability-alert-total">
                <strong>{count(report.quality.open_alerts)}</strong>
                <span>unresolved alerts</span>
              </div>
              <p>
                <strong>
                  {count(report.quality.critical_open_alerts)} critical.
                </strong>{" "}
                A recovered execution retains its failed attempts and does not
                automatically resolve quality incidents.
              </p>
              <button onClick={onDataOperations}>
                Open data operations <ArrowUpRight size={15} />
              </button>
            </section>
          </div>
          <section className="panel">
            <div className="queue-heading">
              <div>
                <span className="eyebrow">WORKER PRESENCE</span>
                <h2>Workers and lease recovery</h2>
              </div>
              <span className="role-badge">
                {count(healthy)} / {count(report.workers.length)} healthy at
                sample
              </span>
            </div>
            <p>
              A worker is healthy when it reports idle or running within{" "}
              {report.limits.heartbeat_stale_seconds} seconds. Stopped,
              degraded, and stale records remain distinguishable. Presence is
              transient telemetry; execution and audit history are durable.
            </p>
            {!report.workers.length ? (
              <p className="reliability-empty">
                No workers have reported presence. Start the worker and refresh
                to verify it can reach PostgreSQL.
              </p>
            ) : (
              <div className="reliability-workers">
                {report.workers.map((worker) => (
                  <article
                    key={worker.worker_id}
                    className="reliability-worker"
                  >
                    <div className="queue-heading">
                      <div>
                        <h3>{worker.instance_id}</h3>
                        <code>{worker.worker_id}</code>
                      </div>
                      <span
                        className={`reliability-worker-state ${worker.healthy ? "reliability-worker-healthy" : "reliability-worker-unhealthy"}`}
                      >
                        {worker.healthy
                          ? "Healthy"
                          : worker.age_seconds >=
                              report.limits.heartbeat_stale_seconds
                            ? "Stale heartbeat"
                            : "Not ready"}{" "}
                        · {worker.state}
                      </span>
                    </div>
                    <dl>
                      <div>
                        <dt>Last heartbeat</dt>
                        <dd>
                          <time dateTime={worker.heartbeat_at}>
                            {date(worker.heartbeat_at)}
                          </time>{" "}
                          · {elapsed(worker.age_seconds)} before sample
                        </dd>
                      </div>
                      <div>
                        <dt>Worker started</dt>
                        <dd>{date(worker.started_at)}</dd>
                      </div>
                      <div>
                        <dt>Execution</dt>
                        <dd>
                          {worker.execution_id ? (
                            <code>{worker.execution_id}</code>
                          ) : (
                            "No active execution reported"
                          )}
                        </dd>
                      </div>
                    </dl>
                  </article>
                ))}
              </div>
            )}
          </section>
          <section className="panel reliability-architecture">
            <div className="queue-heading">
              <div>
                <span className="eyebrow">ARCHITECTURE IN PRACTICE</span>
                <h2>One database, explicit trust boundaries</h2>
              </div>
              <Database aria-hidden="true" size={22} />
            </div>
            <ol>
              <li>
                <strong>React workspace</strong>
                <span>
                  Session cookie, CSRF on changes, accessible evidence views.
                </span>
              </li>
              <li>
                <strong>FastAPI control plane</strong>
                <span>
                  Backend roles and revisions; restricted API database login.
                </span>
              </li>
              <li>
                <strong>PostgreSQL + worker</strong>
                <span>
                  Durable claims, leases, fenced publication and append-only
                  decisions.
                </span>
              </li>
            </ol>
            <p>
              At-least-once execution with idempotent publication. Retries may
              repeat source requests; committed snapshots and their execution
              checkpoints are reconciled together.
            </p>
            <div className="reliability-source-note">
              <strong>Keep the evidence separate.</strong> Synthetic provider
              scores are educational. Artificial fixtures exercise deterministic
              changes and failures. Public CMS archives retain captured
              provenance and are replayed offline; replay does not establish
              current CMS data or clinical quality.
            </div>
          </section>
        </>
      )}
    </div>
  );
}
