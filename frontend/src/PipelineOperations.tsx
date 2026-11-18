import { useEffect, useRef, useState } from "react";
import { Activity, Clock3, Play, RefreshCw } from "lucide-react";
import { authenticatedMutation, AuthMutationError, useAuth } from "./Auth";
import { useApi } from "./api";

type Source = "cms" | "fixture_a" | "fixture_b" | "fixture_retry";
type Config = {
  name: string;
  source: Source;
  max_rows: number;
  enabled: boolean;
  interval_seconds: number;
  max_attempts: number;
  backoff_seconds: number;
  timeout_seconds: number;
};
type Pipeline = Config & {
  id: string;
  revision: number;
  next_run_at: string | null;
  created_at: string;
  updated_at: string;
  latest_execution: Execution | null;
};
type Execution = {
  id: string;
  pipeline_id: string;
  pipeline_name: string;
  status: string;
  revision: number;
  trigger: string;
  scheduled_for: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  available_at: string;
  heartbeat_at: string | null;
  lease_expires_at: string | null;
  attempt_count: number;
  max_attempts: number;
  error_code: string | null;
  published_run_id: string | null;
  snapshot_id: string | null;
  duration_seconds: number | null;
  config: Config;
};
type Detail = Execution & {
  attempts: {
    id: string;
    number: number;
    worker_id: string;
    status: string;
    started_at: string;
    finished_at: string | null;
    heartbeat_at: string | null;
    lease_expires_at: string | null;
    error_code: string | null;
    ingestion_run_id: string | null;
    duration_seconds: number | null;
  }[];
  events: {
    id: string;
    created_at: string;
    action: string;
    from_status: string | null;
    to_status: string | null;
    actor_user_id: string | null;
    details: Record<string, unknown>;
  }[];
};
type Evidence = (
  runId: string,
  snapshotId: string | null,
  mode: "cms" | "fixture",
) => void;
const sources: Record<Source, string> = {
  cms: "Live CMS registry",
  fixture_a: "Deterministic fixture A",
  fixture_b: "Deterministic fixture B",
  fixture_retry: "Development recovery demo",
};
const states = [
  "queued",
  "running",
  "retry_wait",
  "succeeded",
  "failed",
  "cancelled",
  "timed_out",
];
const label = (value: string) => value.replaceAll("_", " ");
const date = (value: string | null) =>
  value ? new Date(value).toLocaleString() : "—";
const short = (value: string) => value.slice(0, 8);
const duration = (value: number | null) =>
  value === null ? "—" : `${value.toFixed(1)}s`;
const active = (value: string) =>
  ["queued", "running", "retry_wait"].includes(value);

// Keep the last successful response visible while polling, without showing a
// different filter's data. Failed refreshes are surfaced and controls disabled.
function useRetainedApi<T>(url: string, refresh: number) {
  const response = useApi<T>(url, refresh);
  const [responseUrl, setResponseUrl] = useState(url);
  const [previous, setPrevious] = useState<{ url: string; data: T } | null>(
    null,
  );
  useEffect(() => {
    if (responseUrl !== url) {
      setResponseUrl(url);
      return;
    }
    if (response.data) setPrevious({ url, data: response.data });
  }, [response.data, url, responseUrl]);
  return {
    ...response,
    data:
      responseUrl === url
        ? response.data || (previous?.url === url ? previous.data : null)
        : null,
  };
}
function Status({ value }: { value: string }) {
  return (
    <span className={`pipeline-status pipeline-status-${value}`}>
      {label(value)}
    </span>
  );
}

export default function PipelineOperations({
  onEvidence,
}: {
  onEvidence: Evidence;
}) {
  const auth = useAuth();
  const administrator = auth?.user.role === "administrator";
  const operator = administrator || auth?.user.role === "analyst";
  const [refresh, setRefresh] = useState(0);
  const [automatic, setAutomatic] = useState(true);
  const [pipelineId, setPipelineId] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const requestKeys = useRef<Record<string, string>>({});
  const pipelines = useRetainedApi<{
    items: Pipeline[];
    demo_enabled: boolean;
  }>("/api/operations/pipelines", refresh);
  const params = new URLSearchParams({ limit: "50", offset: String(offset) });
  if (pipelineId) params.set("pipeline_id", pipelineId);
  if (status) params.set("status", status);
  const executions = useRetainedApi<{
    items: Execution[];
    total: number;
    metrics: Record<string, number>;
  }>(`/api/operations/executions?${params}`, refresh);
  useEffect(() => {
    if (!automatic) return;
    const interval = window.setInterval(() => {
      if (document.visibilityState !== "hidden") setRefresh((n) => n + 1);
    }, 10000);
    return () => window.clearInterval(interval);
  }, [automatic]);
  useEffect(() => {
    if (!selected && executions.data?.items.length)
      setSelected(executions.data.items[0].id);
  }, [selected, executions.data]);
  function refreshNow() {
    setRefresh((n) => n + 1);
  }
  function failed(cause: unknown) {
    setNotice("");
    setError(
      cause instanceof Error
        ? cause.message
        : "The operation could not be completed.",
    );
    if (cause instanceof AuthMutationError && cause.status === 409)
      refreshNow();
  }
  async function request(
    url: string,
    body: Record<string, unknown>,
    idempotent = false,
  ) {
    if (!auth || busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    const key = `${url}:${body.expected_revision ?? "trigger"}`;
    if (idempotent) requestKeys.current[key] ||= crypto.randomUUID();
    try {
      const result: Execution = await authenticatedMutation(
        url,
        auth.csrf_token,
        {
          ...body,
          ...(idempotent ? { idempotency_key: requestKeys.current[key] } : {}),
        },
      );
      delete requestKeys.current[key];
      setSelected(result.id);
      setNotice(
        result.status === "cancelled"
          ? "Execution cancelled. Its history is retained."
          : "Execution accepted. Follow its progress below.",
      );
      refreshNow();
    } catch (cause) {
      failed(cause);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="pipeline-operations">
      <div className="heading">
        <div>
          <span className="eyebrow">DATA PLATFORM · OPERATIONS</span>
          <h1>Pipeline operations</h1>
          <p>
            Schedule ingestion, follow each attempt, and recover with the
            evidence intact.
          </p>
        </div>
        <button onClick={refreshNow} disabled={busy}>
          <RefreshCw size={16} />
          Refresh operations
        </button>
      </div>
      <div className="pipeline-toolbar">
        <span className="role-badge">
          {auth?.user.role || "Read-only"} access
        </span>
        <label>
          <input
            type="checkbox"
            checked={automatic}
            onChange={(event) => setAutomatic(event.target.checked)}
          />
          Refresh every 10 seconds
        </label>
        {!operator && (
          <span>
            View schedules and history. An Analyst or Administrator can control
            executions.
          </span>
        )}
      </div>
      {notice && (
        <p className="save-notice" role="status">
          {notice}
        </p>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error} Refresh the latest state before retrying.
        </p>
      )}
      <div className="pipeline-metrics" aria-label="Execution state totals">
        {[
          "queued",
          "running",
          "retry_wait",
          "succeeded",
          "failed",
          "timed_out",
        ].map((state) => (
          <div key={state}>
            <span>{label(state)}</span>
            <strong>{executions.data?.metrics[state] ?? "—"}</strong>
          </div>
        ))}
      </div>
      <section className="panel">
        <div className="queue-heading">
          <div>
            <span className="eyebrow">DURABLE DEFINITIONS</span>
            <h2>Pipeline schedules</h2>
          </div>
          <Clock3 size={22} aria-hidden="true" />
        </div>
        <p>
          Pausing a schedule stops future automatic runs. Existing executions
          remain in their recorded state.
        </p>
        {pipelines.error && (
          <p role="alert">Schedules could not refresh: {pipelines.error}</p>
        )}
        {!pipelines.data ? (
          <p role="status">Loading pipeline schedules…</p>
        ) : (
          <>
            {!pipelines.data.items.length && (
              <p className="pipeline-empty">
                No pipelines yet. An Administrator can create a schedule below.
              </p>
            )}
            <div className="pipeline-definition-list">
              {pipelines.data.items.map((pipeline) => (
                <article className="pipeline-definition" key={pipeline.id}>
                  <div className="queue-heading">
                    <div>
                      <h3>{pipeline.name}</h3>
                      <p>
                        {sources[pipeline.source]} ·{" "}
                        {pipeline.max_rows.toLocaleString()} requested rows
                      </p>
                    </div>
                    <span
                      className={`pipeline-status ${pipeline.enabled ? "pipeline-status-succeeded" : "pipeline-status-cancelled"}`}
                    >
                      {pipeline.enabled
                        ? "Schedule enabled"
                        : "Schedule paused"}
                    </span>
                  </div>
                  <dl className="pipeline-facts">
                    <div>
                      <dt>Interval</dt>
                      <dd>
                        {pipeline.interval_seconds.toLocaleString()} seconds
                      </dd>
                    </div>
                    <div>
                      <dt>Next scheduled run</dt>
                      <dd>
                        {pipeline.enabled
                          ? date(pipeline.next_run_at)
                          : "Paused"}
                      </dd>
                    </div>
                    <div>
                      <dt>Latest execution</dt>
                      <dd>
                        {pipeline.latest_execution ? (
                          <button
                            className="text-button"
                            onClick={() =>
                              setSelected(pipeline.latest_execution!.id)
                            }
                          >
                            <Status value={pipeline.latest_execution.status} />
                            {short(pipeline.latest_execution.id)}
                          </button>
                        ) : (
                          "No executions"
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt>Recovery policy</dt>
                      <dd>
                        {pipeline.max_attempts} attempts ·{" "}
                        {pipeline.backoff_seconds}s initial backoff ·{" "}
                        {pipeline.timeout_seconds}s timeout
                      </dd>
                    </div>
                  </dl>
                  {pipeline.source === "fixture_retry" && (
                    <p className="pipeline-caveat">
                      Development demo: the first attempt fails deliberately;
                      later attempts use fixture A. No live CMS request is made.
                    </p>
                  )}
                  {operator && (
                    <button
                      disabled={busy || !!pipelines.error}
                      onClick={() =>
                        request(
                          `/api/operations/pipelines/${pipeline.id}/trigger`,
                          {},
                          true,
                        )
                      }
                    >
                      <Play size={15} />
                      Run {pipeline.name} now
                    </button>
                  )}
                  {administrator && !pipelines.error && (
                    <details className="pipeline-edit">
                      <summary>Edit schedule and recovery policy</summary>
                      <ConfigurationForm
                        key={`${pipeline.id}-${pipeline.revision}`}
                        pipeline={pipeline}
                        demoEnabled={!!pipelines.data?.demo_enabled}
                        onSaved={() => {
                          setNotice("Pipeline settings saved.");
                          setError("");
                          refreshNow();
                        }}
                        onError={failed}
                      />
                    </details>
                  )}
                </article>
              ))}
            </div>
            {administrator && !pipelines.error && (
              <details
                className="pipeline-edit"
                open={!pipelines.data.items.length}
              >
                <summary>Create a pipeline</summary>
                <ConfigurationForm
                  demoEnabled={!!pipelines.data?.demo_enabled}
                  onSaved={() => {
                    setNotice(
                      "Pipeline created. Enable its schedule or run it manually.",
                    );
                    setError("");
                    refreshNow();
                  }}
                  onError={failed}
                />
              </details>
            )}
          </>
        )}
      </section>
      <section className="panel">
        <div className="queue-heading">
          <div>
            <span className="eyebrow">EXECUTION HISTORY</span>
            <h2>Every run, every attempt</h2>
          </div>
          <Activity size={22} aria-hidden="true" />
        </div>
        <div className="pipeline-filters">
          <label>
            Pipeline
            <select
              value={pipelineId}
              onChange={(event) => {
                setPipelineId(event.target.value);
                setOffset(0);
                setSelected("");
              }}
            >
              <option value="">All pipelines</option>
              {pipelines.data?.items.map((pipeline) => (
                <option value={pipeline.id} key={pipeline.id}>
                  {pipeline.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Execution status
            <select
              value={status}
              onChange={(event) => {
                setStatus(event.target.value);
                setOffset(0);
                setSelected("");
              }}
            >
              <option value="">All statuses</option>
              {states.map((state) => (
                <option value={state} key={state}>
                  {label(state)}
                </option>
              ))}
            </select>
          </label>
        </div>
        {executions.error && (
          <p role="alert">
            Execution history could not refresh: {executions.error}
          </p>
        )}
        {!executions.data ? (
          <p role="status">Loading execution history…</p>
        ) : (
          <>
            {!executions.data.items.length ? (
              <p className="pipeline-empty">
                No executions match these filters.
              </p>
            ) : (
              <div className="table-scroll">
                <table className="pipeline-table">
                  <thead>
                    <tr>
                      <th>Execution / pipeline</th>
                      <th>State</th>
                      <th>Attempts</th>
                      <th>Created</th>
                      <th>Duration</th>
                    </tr>
                  </thead>
                  <tbody>
                    {executions.data.items.map((execution) => (
                      <tr
                        key={execution.id}
                        className={
                          selected === execution.id ? "pipeline-selected" : ""
                        }
                      >
                        <td>
                          <button
                            className="text-button"
                            aria-label={`Inspect execution ${short(execution.id)}`}
                            aria-pressed={selected === execution.id}
                            onClick={() => setSelected(execution.id)}
                          >
                            {execution.pipeline_name}
                            <small>
                              {short(execution.id)} · {label(execution.trigger)}
                            </small>
                          </button>
                        </td>
                        <td>
                          <Status value={execution.status} />
                          {execution.error_code && (
                            <small className="pipeline-error-code">
                              {label(execution.error_code)}
                            </small>
                          )}
                        </td>
                        <td>
                          {execution.attempt_count} / {execution.max_attempts}
                        </td>
                        <td>{date(execution.created_at)}</td>
                        <td>{duration(execution.duration_seconds)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="pipeline-history-count">
              Showing {executions.data.items.length ? offset + 1 : 0}–
              {offset + executions.data.items.length} of {executions.data.total}{" "}
              executions.
            </p>
            <div
              className="pipeline-toolbar"
              aria-label="Execution history pages"
            >
              <button
                disabled={offset === 0 || executions.loading}
                onClick={() => {
                  setOffset(Math.max(0, offset - 50));
                  setSelected("");
                }}
              >
                Newer executions
              </button>
              <button
                disabled={
                  offset + 50 >= executions.data.total || executions.loading
                }
                onClick={() => {
                  setOffset(offset + 50);
                  setSelected("");
                }}
              >
                Older executions
              </button>
            </div>
          </>
        )}
      </section>
      {selected && (
        <ExecutionDetail
          key={selected}
          id={selected}
          refresh={refresh}
          operator={!!operator}
          busy={busy}
          request={request}
          onEvidence={onEvidence}
        />
      )}
    </div>
  );
}

function ConfigurationForm({
  pipeline,
  demoEnabled,
  onSaved,
  onError,
}: {
  pipeline?: Pipeline;
  demoEnabled: boolean;
  onSaved: () => void;
  onError: (cause: unknown) => void;
}) {
  const auth = useAuth()!;
  const initial: Config = pipeline || {
    name: "",
    source: "fixture_a",
    max_rows: 5,
    enabled: false,
    interval_seconds: 3600,
    max_attempts: 3,
    backoff_seconds: 5,
    timeout_seconds: 120,
  };
  const [values, setValues] = useState<Config>(initial);
  const [busy, setBusy] = useState(false);
  function change<K extends keyof Config>(key: K, value: Config[K]) {
    setValues((current) => ({ ...current, [key]: value }));
  }
  const changed = (
    [
      "name",
      "source",
      "max_rows",
      "enabled",
      "interval_seconds",
      "max_attempts",
      "backoff_seconds",
      "timeout_seconds",
    ] as (keyof Config)[]
  ).some((key) => key in values && initial[key] !== values[key]);
  return (
    <form
      className="pipeline-config"
      aria-label={pipeline ? `Configure ${pipeline.name}` : "Create pipeline"}
      onSubmit={async (event) => {
        event.preventDefault();
        setBusy(true);
        const keys: (keyof Config)[] = [
          "name",
          "source",
          "max_rows",
          "enabled",
          "interval_seconds",
          "max_attempts",
          "backoff_seconds",
          "timeout_seconds",
        ];
        const body = Object.fromEntries(
          keys
            .filter((key) => !pipeline || values[key] !== pipeline[key])
            .map((key) => [key, values[key]]),
        );
        try {
          await authenticatedMutation(
            pipeline
              ? `/api/operations/pipelines/${pipeline.id}`
              : "/api/operations/pipelines",
            auth.csrf_token,
            {
              ...body,
              ...(pipeline ? { expected_revision: pipeline.revision } : {}),
            },
            pipeline ? "PATCH" : "POST",
          );
          if (!pipeline) setValues({ ...initial, name: "" });
          onSaved();
        } catch (cause) {
          onError(cause);
        } finally {
          setBusy(false);
        }
      }}
    >
      <fieldset disabled={busy}>
        <legend>
          {pipeline ? "Schedule settings" : "New pipeline settings"}
        </legend>
        <div className="pipeline-config-grid">
          <label>
            Pipeline name
            <input
              required
              maxLength={100}
              value={values.name}
              onChange={(event) => change("name", event.target.value)}
            />
          </label>
          <label>
            Source
            <select
              value={values.source}
              onChange={(event) =>
                setValues((current) => ({
                  ...current,
                  source: event.target.value as Source,
                  max_rows: event.target.value === "cms" ? 1000 : 5,
                }))
              }
            >
              {Object.entries(sources)
                .filter(([key]) => key !== "fixture_retry" || demoEnabled)
                .map(([key, title]) => (
                  <option key={key} value={key}>
                    {title}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Requested rows
            <input
              required
              type="number"
              min={1}
              max={5000}
              value={values.max_rows}
              onChange={(event) =>
                change("max_rows", Number(event.target.value))
              }
            />
          </label>
          <label>
            Schedule interval (seconds)
            <input
              required
              type="number"
              min={10}
              max={2592000}
              value={values.interval_seconds}
              onChange={(event) =>
                change("interval_seconds", Number(event.target.value))
              }
            />
          </label>
          <label>
            Maximum attempts
            <input
              required
              type="number"
              min={1}
              max={5}
              value={values.max_attempts}
              onChange={(event) =>
                change("max_attempts", Number(event.target.value))
              }
            />
          </label>
          <label>
            Initial backoff (seconds)
            <input
              required
              type="number"
              min={1}
              max={3600}
              value={values.backoff_seconds}
              onChange={(event) =>
                change("backoff_seconds", Number(event.target.value))
              }
            />
          </label>
          <label>
            Execution timeout (seconds)
            <input
              required
              type="number"
              min={5}
              max={600}
              value={values.timeout_seconds}
              onChange={(event) =>
                change("timeout_seconds", Number(event.target.value))
              }
            />
          </label>
          <label className="pipeline-checkbox">
            <input
              type="checkbox"
              checked={values.enabled}
              onChange={(event) => change("enabled", event.target.checked)}
            />
            Enable scheduled ingestion
          </label>
        </div>
        <p>
          Retries use exponential backoff. The attempt limit includes the
          initial attempt. Enabling a schedule makes its first run due
          immediately.
        </p>
        {values.source === "cms" && (
          <p className="pipeline-caveat">
            This source makes live requests to the official CMS registry when
            executed.
          </p>
        )}
        <button
          type="submit"
          disabled={busy || !values.name.trim() || (!!pipeline && !changed)}
        >
          {busy
            ? "Saving…"
            : pipeline
              ? "Save pipeline settings"
              : "Create pipeline"}
        </button>
      </fieldset>
    </form>
  );
}

function ExecutionDetail({
  id,
  refresh,
  operator,
  busy,
  request,
  onEvidence,
}: {
  id: string;
  refresh: number;
  operator: boolean;
  busy: boolean;
  request: (
    url: string,
    body: Record<string, unknown>,
    idempotent?: boolean,
  ) => Promise<void>;
  onEvidence: Evidence;
}) {
  const detail = useRetainedApi<Detail>(
    `/api/operations/executions/${encodeURIComponent(id)}`,
    refresh,
  );
  const [reason, setReason] = useState("");
  const execution = detail.data;
  return (
    <section
      className="panel pipeline-inspection"
      aria-label="Execution inspection"
    >
      <span className="eyebrow">EXECUTION · {short(id)}</span>
      <h2>Execution detail</h2>
      {detail.error && (
        <p role="alert">Execution details could not refresh: {detail.error}</p>
      )}
      {!execution ? (
        <p role="status">Loading execution detail…</p>
      ) : (
        <>
          <div className="queue-heading">
            <h3>{execution.pipeline_name}</h3>
            <Status value={execution.status} />
          </div>
          <dl className="pipeline-facts">
            <div>
              <dt>Requested source</dt>
              <dd>
                {sources[execution.config.source]} · {execution.config.max_rows}{" "}
                rows
              </dd>
            </div>
            <div>
              <dt>Trigger</dt>
              <dd>
                {label(execution.trigger)}
                {execution.scheduled_for &&
                  ` · ${date(execution.scheduled_for)}`}
              </dd>
            </div>
            <div>
              <dt>Started</dt>
              <dd>{date(execution.started_at)}</dd>
            </div>
            <div>
              <dt>Finished</dt>
              <dd>{date(execution.finished_at)}</dd>
            </div>
            <div>
              <dt>Duration</dt>
              <dd>{duration(execution.duration_seconds)}</dd>
            </div>
            <div>
              <dt>Attempts</dt>
              <dd>
                {execution.attempt_count} / {execution.max_attempts}
              </dd>
            </div>
            <div>
              <dt>Last heartbeat</dt>
              <dd>{date(execution.heartbeat_at)}</dd>
            </div>
            <div>
              <dt>Lease expires</dt>
              <dd>{date(execution.lease_expires_at)}</dd>
            </div>
          </dl>
          {execution.status === "running" &&
            execution.lease_expires_at &&
            Date.parse(execution.lease_expires_at) < Date.now() && (
              <p className="pipeline-caveat">
                The worker lease has expired. Waiting for a worker to recover
                this execution.
              </p>
            )}
          {execution.status === "retry_wait" && (
            <p className="pipeline-caveat">
              Retry eligible at {date(execution.available_at)}. A running worker
              will claim it according to its recovery policy.
            </p>
          )}
          {execution.error_code && (
            <p className="pipeline-caveat">
              Recorded failure: <code>{execution.error_code}</code>. Attempt
              history below retains the outcome of each try.
            </p>
          )}
          {execution.published_run_id && (
            <div className="pipeline-evidence">
              <p>
                <strong>Publication recorded.</strong>{" "}
                {execution.snapshot_id
                  ? `Snapshot ${short(execution.snapshot_id)}.`
                  : "See the recorded ingestion result."}{" "}
                {execution.status !== "succeeded" &&
                  "Recovery may still need to reconcile monitoring; published data is retained."}
              </p>
              <button
                onClick={() =>
                  onEvidence(
                    execution.published_run_id!,
                    execution.snapshot_id,
                    execution.config.source === "cms" ? "cms" : "fixture",
                  )
                }
              >
                Inspect ingestion and quality evidence
              </button>
            </div>
          )}
          {operator &&
            !detail.error &&
            ["failed", "timed_out", "cancelled"].includes(execution.status) && (
              <button
                disabled={busy}
                onClick={() =>
                  request(
                    `/api/operations/executions/${id}/retry`,
                    { expected_revision: execution.revision },
                    true,
                  )
                }
              >
                Retry execution
              </button>
            )}
          {operator &&
            !detail.error &&
            active(execution.status) &&
            !execution.published_run_id && (
              <form
                className="pipeline-cancel"
                onSubmit={(event) => {
                  event.preventDefault();
                  request(`/api/operations/executions/${id}/cancel`, {
                    expected_revision: execution.revision,
                    reason: reason.trim(),
                  });
                }}
              >
                <label>
                  Cancellation reason
                  <input
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    required
                    minLength={3}
                    maxLength={500}
                    placeholder="Record why this work should stop"
                    disabled={busy}
                  />
                </label>
                <button disabled={busy || reason.trim().length < 3}>
                  Cancel execution
                </button>
              </form>
            )}
          <h3 className="pipeline-subheading">Execution attempts</h3>
          {!execution.attempts.length ? (
            <p>No worker has claimed this execution yet.</p>
          ) : (
            <ol className="monitor-timeline">
              {execution.attempts.map((attempt) => (
                <li key={attempt.id}>
                  <div>
                    <strong>Attempt {attempt.number}</strong>{" "}
                    <Status value={attempt.status} />
                  </div>
                  <p>
                    {date(attempt.started_at)} →{" "}
                    {attempt.finished_at
                      ? date(attempt.finished_at)
                      : "In progress"}{" "}
                    · {duration(attempt.duration_seconds)}
                  </p>
                  <small>
                    Worker {attempt.worker_id} · Last heartbeat{" "}
                    {date(attempt.heartbeat_at)}
                  </small>
                  {attempt.error_code && (
                    <p>
                      Failure: <code>{attempt.error_code}</code>
                    </p>
                  )}
                  {attempt.ingestion_run_id && (
                    <button
                      className="text-button"
                      onClick={() =>
                        onEvidence(
                          attempt.ingestion_run_id!,
                          null,
                          execution.config.source === "cms" ? "cms" : "fixture",
                        )
                      }
                    >
                      Inspect attempt ingestion{" "}
                      {short(attempt.ingestion_run_id)}
                    </button>
                  )}
                </li>
              ))}
            </ol>
          )}
          <h3 className="pipeline-subheading">
            Recorded decisions and state changes
          </h3>
          {!execution.events.length ? (
            <p>No events recorded.</p>
          ) : (
            <ol className="monitor-timeline">
              {execution.events.map((event) => (
                <li key={event.id}>
                  <strong>{label(event.action)}</strong>
                  <p>
                    {event.from_status && `${label(event.from_status)} → `}
                    {event.to_status
                      ? label(event.to_status)
                      : "Configuration recorded"}
                  </p>
                  <small>
                    {date(event.created_at)} ·{" "}
                    {event.actor_user_id
                      ? `Authenticated account ${event.actor_user_id}`
                      : "Scheduler / worker"}
                  </small>
                  {Object.keys(event.details).length > 0 && (
                    <details>
                      <summary>Recorded context</summary>
                      <pre className="dataops-code">
                        {JSON.stringify(event.details, null, 2)}
                      </pre>
                    </details>
                  )}
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </section>
  );
}
