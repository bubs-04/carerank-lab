import { useState } from "react";
import Monitoring from "./Monitoring";
import { useApi } from "./api";

type Run = {
  id: string;
  status: string;
  started_at: string;
  seconds: number | null;
  snapshot_id: string | null;
  requested: number;
  received: number | null;
  valid: number | null;
  rejected: number | null;
  warnings: number | null;
  error_code: string | null;
  provenance: Record<string, unknown>;
};
type Version = {
  id: string;
  created_at: string;
  checksum: string;
  received: number;
  valid: number;
  rejected: number;
  warnings: number;
  policy: string;
  scope: { max_rows: number };
  provenance: Record<string, unknown>;
};
type Page<T> = { items: T[]; total: number; page: number; page_size: number };
type Status = {
  sources: { id: string; title: string; mode: string; url: string }[];
  latest_attempt: Run | null;
  latest_success: Run | null;
  snapshot_count: number;
};
type Finding = {
  row_number: number | null;
  severity: string;
  code: string;
  field: string;
};
type RecordRow = {
  row_number: number;
  accepted: boolean;
  record_key: string;
  data: Record<string, string>;
};
type Comparison = {
  added: number;
  removed: number;
  changed: number;
  unchanged: number;
  specialty_changes: number;
  location_changes: number;
  validation_delta: Record<string, number>;
  caveat: string;
  examples: {
    record_key: string;
    fields: string[];
    before: Record<string, string>;
    after: Record<string, string>;
  }[];
  examples_truncated: boolean;
};
const statusLabel = (status: string) =>
  status === "no_change" ? "Version reused" : status;
const short = (id: string) => id.slice(0, 8);
const date = (s: string) => new Date(s).toLocaleString();
const archived = (provenance?: Record<string, unknown>) =>
  provenance?.archive_replay === true;
function ArchiveNotice({
  provenance,
}: {
  provenance?: Record<string, unknown>;
}) {
  if (!archived(provenance)) return null;
  return (
    <p className="pipeline-caveat">
      <strong>Archived public CMS data.</strong> Replayed offline from an
      archived official source response.
      {typeof provenance?.archive_captured_at === "string" && (
        <>
          {" "}
          Captured{" "}
          <time dateTime={provenance.archive_captured_at}>
            {date(provenance.archive_captured_at)}
          </time>
          .
        </>
      )}{" "}
      This is not a fresh live retrieval and does not establish current CMS
      data.
    </p>
  );
}
function Load({ error }: { error: string }) {
  return (
    <p role={error ? "alert" : "status"}>
      {error
        ? `Unable to load Data Operations: ${error}. Check API health and migration 002, then refresh.`
        : "Loading data operations…"}
    </p>
  );
}
function Pager({
  page,
  total,
  size,
  setPage,
}: {
  page: number;
  total: number;
  size: number;
  setPage: (p: number) => void;
}) {
  return (
    <div className="pagination">
      <span>
        Page {page} of {Math.max(1, Math.ceil(total / size))} · {total} records
      </span>
      <div>
        <button disabled={page === 1} onClick={() => setPage(page - 1)}>
          Previous
        </button>
        <button
          disabled={page * size >= total}
          onClick={() => setPage(page + 1)}
        >
          Next
        </button>
      </div>
    </div>
  );
}
export function CountChart({
  items,
  label,
}: {
  items: { name: string; count: number }[];
  label: string;
}) {
  const max = Math.max(1, ...items.map((i) => i.count));
  return (
    <div className="bars" role="group" aria-label={label}>
      {items.map((i) => (
        <div className="bar-row" key={i.name}>
          <span>{i.name}</span>
          <div className="bar-track" title={`${i.name}: ${i.count}`}>
            <div style={{ width: `${(100 * i.count) / max}%` }} />
          </div>
          <b>{i.count}</b>
        </div>
      ))}
    </div>
  );
}
function Findings({ runId }: { runId: string }) {
  const [page, setPage] = useState(1);
  const result = useApi<Page<Finding>>(
    `/api/dataops/runs/${encodeURIComponent(runId)}/findings?page=${page}&page_size=50`,
  );
  return (
    <section className="panel">
      <h2>Validation findings · run {short(runId)}</h2>
      <p>
        Row numbers refer to the captured CSV prefix. A row can have several
        findings. Warning counts are not additional rejected records.
      </p>
      {!result.data ? (
        <Load error={result.error} />
      ) : (
        <>
          {!result.data.total ? (
            <p>No validation findings for this run.</p>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Source row</th>
                    <th>Severity</th>
                    <th>Rule</th>
                    <th>Field</th>
                  </tr>
                </thead>
                <tbody>
                  {result.data.items.map((f, i) => (
                    <tr key={i}>
                      <td>{f.row_number ?? "Whole batch"}</td>
                      <td>{f.severity}</td>
                      <td>{f.code}</td>
                      <td>{f.field}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Pager
            page={page}
            total={result.data.total}
            size={50}
            setPage={setPage}
          />
        </>
      )}
    </section>
  );
}
function Records({ versionId }: { versionId: string }) {
  const [page, setPage] = useState(1);
  const result = useApi<Page<RecordRow>>(
    `/api/dataops/versions/${encodeURIComponent(versionId)}/records?page=${page}&page_size=50`,
  );
  return (
    <section className="panel">
      <h2>Captured registry records · {short(versionId)}</h2>
      <p>
        Includes accepted and rejected projected records. No patient data, phone
        numbers, street lines or synthetic scores.
      </p>
      {!result.data ? (
        <Load error={result.error} />
      ) : (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Row / status</th>
                  <th>NPI</th>
                  <th>Enrollment</th>
                  <th>Group / address key</th>
                  <th>Specialty</th>
                  <th>City / state</th>
                </tr>
              </thead>
              <tbody>
                {result.data.items.map((r) => (
                  <tr key={r.row_number}>
                    <td>
                      {r.row_number} · {r.accepted ? "Accepted" : "Rejected"}
                    </td>
                    <td>{r.data.npi || "Missing"}</td>
                    <td>{r.data.ind_enrl_id}</td>
                    <td>
                      {r.data.org_pac_id || "No group"}
                      <br />
                      {r.data.adrs_id}
                    </td>
                    <td>{r.data.pri_spec || "Not supplied"}</td>
                    <td>
                      {r.data.citytown || "Not supplied"} /{" "}
                      {r.data.state || "Not supplied"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager
            page={page}
            total={result.data.total}
            size={50}
            setPage={setPage}
          />
        </>
      )}
    </section>
  );
}
function Compare({ oldId, newId }: { oldId: string; newId: string }) {
  const result = useApi<Comparison>(
    `/api/dataops/compare?${new URLSearchParams({ old_id: oldId, new_id: newId })}`,
  );
  if (!result.data) return <Load error={result.error} />;
  const d = result.data;
  return (
    <>
      <CountChart
        label="Accepted-record changes in captured samples"
        items={[
          { name: "Added", count: d.added },
          { name: "Removed", count: d.removed },
          { name: "Changed", count: d.changed },
          { name: "Unchanged", count: d.unchanged },
        ]}
      />
      <p>
        {d.specialty_changes} specialty changes · {d.location_changes}{" "}
        city/state changes among retained identities.
      </p>
      <p className="caption">{d.caveat}</p>
      <details>
        <summary>Validation differences and changed-record examples</summary>
        <p>
          Finding count deltas (new minus old):{" "}
          {Object.entries(d.validation_delta)
            .map(([k, v]) => `${k}: ${v > 0 ? "+" : ""}${v}`)
            .join("; ") || "None"}
        </p>
        {d.examples.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>NPI / source key</th>
                  <th>Field</th>
                  <th>Before</th>
                  <th>After</th>
                </tr>
              </thead>
              <tbody>
                {d.examples.flatMap((c) =>
                  c.fields.map((f) => (
                    <tr key={`${c.record_key}-${f}`}>
                      <td>
                        {c.after.npi}
                        <br />
                        {short(c.record_key)}
                      </td>
                      <td>{f}</td>
                      <td>{c.before[f] || "Not supplied"}</td>
                      <td>{c.after[f] || "Not supplied"}</td>
                    </tr>
                  )),
                )}
              </tbody>
            </table>
          </div>
        ) : (
          <p>No tracked field changes among retained accepted identities.</p>
        )}
        {d.examples_truncated && (
          <p>First 50 changed records shown; chart counts include all.</p>
        )}
      </details>
    </>
  );
}
function Attempt({ runId }: { runId: string }) {
  const result = useApi<Run>(
    `/api/dataops/monitoring/runs/${encodeURIComponent(runId)}`,
  );
  return result.data ? (
    <>
      <p>
        {result.data.status} · requested {result.data.requested} · received{" "}
        {result.data.received ?? "unknown"} · error{" "}
        {result.data.error_code || "none recorded"}
      </p>
      <ArchiveNotice provenance={result.data.provenance} />
    </>
  ) : (
    <Load error={result.error} />
  );
}
function Workspace({
  mode,
  inspect,
}: {
  mode: "cms" | "fixture";
  inspect: { runId: string; snapshotId?: string | null };
}) {
  const [versionPage, setVersionPage] = useState(1),
    [runPage, setRunPage] = useState(1);
  const [older, setOlder] = useState<string>(""),
    [newer, setNewer] = useState<string>("");
  const [findingRun, setFindingRun] = useState(inspect.runId),
    [recordVersion, setRecordVersion] = useState(inspect.snapshotId || "");
  const status = useApi<Status>(`/api/dataops/status?mode=${mode}`);
  const versions = useApi<Page<Version>>(
    `/api/dataops/versions?mode=${mode}&page=${versionPage}&page_size=10`,
  );
  const runs = useApi<Page<Run>>(
    `/api/dataops/runs?mode=${mode}&page=${runPage}&page_size=10`,
  );
  const attempt = status.data?.latest_attempt,
    success = status.data?.latest_success;
  return (
    <>
      {inspect.runId && (
        <section className="panel">
          <h2>Selected investigation evidence</h2>
          <p>
            Attempt {inspect.runId}. Its validation findings and any selected
            snapshot records appear below.
          </p>
          <a href="#selected-findings">Jump to selected findings</a>
          {inspect.snapshotId && (
            <p>
              <a href="#selected-records">Jump to selected snapshot records</a>
            </p>
          )}
          <Attempt runId={inspect.runId} />
        </section>
      )}
      <section className="panel">
        <h2>Source and job health</h2>
        <p>
          <a
            href="https://data.cms.gov/provider-data/dataset/mj5m-pzi6"
            target="_blank"
            rel="noreferrer"
          >
            CMS Doctors and Clinicians National Downloadable File
          </a>{" "}
          · mj5m-pzi6
        </p>
        <p>
          Identity: NPI + enrollment + group (may be blank) + address ID. One
          clinician may have several source records.
        </p>
        {!status.data ? (
          <Load error={status.error} />
        ) : (
          <>
            <div className="metrics">
              <section className="metric">
                <div>Latest attempt</div>
                <strong className="dataops-status">
                  {attempt ? statusLabel(attempt.status) : "No runs"}
                </strong>
                <small>
                  {attempt
                    ? date(attempt.started_at)
                    : "CLI ingestion has not run"}
                </small>
              </section>
              <section className="metric">
                <div>Latest published version</div>
                <strong className="dataops-status">
                  {success ? short(success.snapshot_id ?? "") : "None"}
                </strong>
                <small>
                  {success ? date(success.started_at) : "No published snapshot"}
                </small>
              </section>
              <section className="metric">
                <div>Versions retained</div>
                <strong>{status.data.snapshot_count}</strong>
                <small>Matching prior content reuses a version</small>
              </section>
              <section className="metric">
                <div>Attempt duration</div>
                <strong>{attempt?.seconds?.toFixed(2) ?? "—"}</strong>
                <small>seconds · pending if still running</small>
              </section>
            </div>
            <ArchiveNotice
              provenance={
                archived(success?.provenance)
                  ? success?.provenance
                  : attempt?.provenance
              }
            />
            {attempt ? (
              <>
                <p>
                  Requested {attempt.requested} rows · received{" "}
                  {attempt.received ?? "unknown"} ·{" "}
                  {attempt.warnings ?? "unknown"} warning findings.
                </p>
                {attempt.error_code && (
                  <p role="alert">
                    Attempt failed: {attempt.error_code}. Earlier successful
                    snapshots remain available.
                  </p>
                )}
                {attempt.valid !== null && attempt.rejected !== null && (
                  <>
                    <h3>Attempt validation outcomes</h3>
                    <CountChart
                      label="Accepted versus rejected record counts"
                      items={[
                        { name: "Valid", count: attempt.valid },
                        { name: "Rejected", count: attempt.rejected },
                      ]}
                    />
                    <p className="caption">
                      Validation counts do not by themselves mean the snapshot
                      was published. Check the run status above.
                    </p>
                  </>
                )}
                <button onClick={() => setFindingRun(attempt.id)}>
                  Inspect latest findings
                </button>
              </>
            ) : (
              <p>
                No {mode === "cms" ? "CMS" : "fixture"} ingestion yet. Run the
                CLI below; this page cannot start external jobs.
              </p>
            )}
            <details>
              <summary>CLI command and source provenance</summary>
              <pre className="dataops-code">
                {mode === "cms"
                  ? "docker compose run --rm --no-deps api python -m app.ingestion --max-rows 1000"
                  : "docker compose run --rm --no-deps api python -m app.ingestion --fixture tests/fixtures/cms_registry_a.csv --max-rows 5"}
              </pre>
              <p>
                Run migration 002 first. Refresh this page after the job
                completes. Bounded source-order samples are not national
                censuses.
              </p>
              {attempt && (
                <dl className="dataops-provenance">
                  <dt>Release (if supplied)</dt>
                  <dd>
                    {String(attempt.provenance.release ?? "Not supplied")}
                  </dd>
                  <dt>Modified</dt>
                  <dd>
                    {String(attempt.provenance.modified ?? "Not supplied")}
                  </dd>
                  <dt>Distribution</dt>
                  <dd>
                    {String(
                      attempt.provenance.distribution_id ??
                        "Fixture / not supplied",
                    )}
                  </dd>
                  <dt>Retrieval method</dt>
                  <dd>
                    {String(
                      attempt.provenance.retrieval_method ?? "Not available",
                    )}
                  </dd>
                </dl>
              )}
            </details>
          </>
        )}
      </section>
      <section className="panel">
        <h2>Dataset version history</h2>
        {!versions.data ? (
          <Load error={versions.error} />
        ) : (
          <>
            {versions.data.items.length === 0 ? (
              <p>No successful snapshots yet.</p>
            ) : (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Version / published</th>
                      <th>Release / scope</th>
                      <th>Valid / rejected</th>
                      <th>Checksum / policy</th>
                      <th>Inspect / compare</th>
                    </tr>
                  </thead>
                  <tbody>
                    {versions.data.items.map((v) => (
                      <tr key={v.id}>
                        <td title={v.id}>
                          {short(v.id)}
                          <br />
                          {date(v.created_at)}
                          {archived(v.provenance) && (
                            <small className="provider-sub">
                              Archived public CMS data
                            </small>
                          )}
                        </td>
                        <td>
                          {String(v.provenance.release ?? "Not supplied")}
                          <br />
                          First {v.scope.max_rows} rows
                        </td>
                        <td>
                          {v.valid} / {v.rejected}
                        </td>
                        <td>
                          <details>
                            <summary>SHA-256 · {short(v.checksum)}</summary>
                            <code className="checksum">{v.checksum}</code>
                          </details>
                          {v.policy}
                        </td>
                        <td>
                          <div className="dataops-actions">
                            <button
                              onClick={() => setRecordVersion(v.id)}
                              aria-label={`Inspect version ${short(v.id)}`}
                            >
                              Records
                            </button>
                            <button
                              onClick={() => setOlder(v.id)}
                              aria-label={`Set older ${short(v.id)}`}
                            >
                              Set older
                            </button>
                            <button
                              onClick={() => setNewer(v.id)}
                              aria-label={`Set newer ${short(v.id)}`}
                            >
                              Set newer
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <Pager
              page={versionPage}
              total={versions.data.total}
              size={10}
              setPage={setVersionPage}
            />
          </>
        )}
      </section>
      <section className="panel">
        <h2>Compare captured versions</h2>
        <p>
          Older: {older ? short(older) : "Select in history"} → Newer:{" "}
          {newer ? short(newer) : "Select in history"}
        </p>
        {older && newer ? (
          <Compare key={`${older}-${newer}`} oldId={older} newId={newer} />
        ) : (
          <p>
            Select two versions with the same source, row limit and validation
            policy. Direction follows your selection; same-version comparison is
            permitted.
          </p>
        )}
      </section>
      <section className="panel">
        <h2>Ingestion attempts</h2>
        {!runs.data ? (
          <Load error={runs.error} />
        ) : (
          <>
            {!runs.data.items.length ? (
              <p>No attempts recorded.</p>
            ) : (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Started / run</th>
                      <th>Status</th>
                      <th>Rows valid / rejected</th>
                      <th>Duration</th>
                      <th>Findings</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.data.items.map((r) => (
                      <tr key={r.id}>
                        <td>
                          {date(r.started_at)}
                          <br />
                          {short(r.id)}
                        </td>
                        <td>
                          {statusLabel(r.status)}
                          {archived(r.provenance) && (
                            <small className="provider-sub">
                              Archived public CMS data
                            </small>
                          )}
                          {r.error_code && (
                            <small className="provider-sub">
                              {r.error_code}
                            </small>
                          )}
                        </td>
                        <td>
                          {r.valid ?? "—"} / {r.rejected ?? "—"}
                        </td>
                        <td>{r.seconds?.toFixed(2) ?? "—"} s</td>
                        <td>
                          <button
                            onClick={() => setFindingRun(r.id)}
                            aria-label={`Findings for run ${short(r.id)}`}
                          >
                            Findings
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <Pager
              page={runPage}
              total={runs.data.total}
              size={10}
              setPage={setRunPage}
            />
          </>
        )}
      </section>
      {findingRun && (
        <div id="selected-findings">
          <Findings key={findingRun} runId={findingRun} />
        </div>
      )}
      {recordVersion && (
        <div id="selected-records">
          <Records key={recordVersion} versionId={recordVersion} />
        </div>
      )}
    </>
  );
}
export default function DataOps({
  initialInspection,
}: {
  initialInspection?: {
    runId: string;
    snapshotId: string | null;
    mode: "cms" | "fixture";
  };
} = {}) {
  const [mode, setMode] = useState<"cms" | "fixture">(
    initialInspection?.mode || "cms",
  );
  const [refreshKey, setRefreshKey] = useState(0);
  const [tab, setTab] = useState("ingestion");
  const [inspect, setInspect] = useState<{
    runId: string;
    snapshotId?: string | null;
  }>(initialInspection || { runId: "" });
  return (
    <>
      <div className="heading">
        <div>
          <span className="eyebrow">PUBLIC REGISTRY · OPERATIONS</span>
          <h1>Data operations</h1>
          <p>What arrived, what changed, and whether processing succeeded.</p>
        </div>
        <button type="button" onClick={() => setRefreshKey((n) => n + 1)}>
          Refresh status
        </button>
      </div>
      <section className="panel">
        <label className="cohort-filter">
          Data source mode
          <select
            value={mode}
            onChange={(e) => {
              setMode(e.target.value as "cms" | "fixture");
              setInspect({ runId: "" });
            }}
          >
            <option value="cms">Public CMS registry (live or archived)</option>
            <option value="fixture">Deterministic fixture (test data)</option>
          </select>
        </label>
        <p>
          <strong>
            {mode === "fixture"
              ? "Fixture mode: these are artificial test records, not retrieved CMS data."
              : "Public provider registry: no patient records and no clinical ratings."}
          </strong>{" "}
          Registry identities are never joined to the synthetic ranking system.
        </p>
      </section>
      <div
        className="dataops-actions monitor-tabs"
        role="group"
        aria-label="Data operations areas"
      >
        <button
          aria-pressed={tab === "ingestion"}
          onClick={() => setTab("ingestion")}
        >
          Ingestion and versions
        </button>
        <button
          aria-pressed={tab === "monitoring"}
          onClick={() => setTab("monitoring")}
        >
          Quality monitoring
        </button>
      </div>
      {tab === "ingestion" ? (
        <Workspace
          key={`${mode}-${refreshKey}-${inspect.runId}-${inspect.snapshotId}`}
          mode={mode}
          inspect={inspect}
        />
      ) : (
        <Monitoring
          key={`${mode}-${refreshKey}`}
          mode={mode}
          onInspect={(runId, snapshotId) => {
            setInspect({ runId, snapshotId });
            setTab("ingestion");
          }}
        />
      )}
    </>
  );
}
