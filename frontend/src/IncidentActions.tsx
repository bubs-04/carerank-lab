import { useState } from "react";
import type { FormEvent } from "react";
import { authenticatedMutation, useAuth } from "./Auth";
import type { User } from "./Auth";
import { useApi } from "./api";

type Incident = {
  id: string;
  revision: number;
  status: string;
  assigned_to: string | null;
  assigned_user_id?: string | null;
};
const transitions: Record<string, { value: string; label: string }[]> = {
  open: [
    { value: "acknowledged", label: "Acknowledge" },
    { value: "investigating", label: "Start investigation" },
  ],
  acknowledged: [
    { value: "investigating", label: "Start investigation" },
    { value: "resolved", label: "Resolve incident" },
  ],
  investigating: [
    { value: "acknowledged", label: "Return to acknowledged" },
    { value: "resolved", label: "Resolve incident" },
  ],
  resolved: [{ value: "open", label: "Reopen incident" }],
};
export default function IncidentActions({
  incident,
  onSaved,
  onReload,
}: {
  incident: Incident;
  onSaved: () => void;
  onReload: () => void;
}) {
  const auth = useAuth();
  if (!auth || auth.user.role === "viewer")
    return (
      <p className="access-notice">
        <strong>Viewer access.</strong> You can review incidents and their
        history. An Analyst or Administrator can record investigation decisions.
      </p>
    );
  return (
    <ActionForm incident={incident} onSaved={onSaved} onReload={onReload} />
  );
}
function ActionForm({
  incident,
  onSaved,
  onReload,
}: {
  incident: Incident;
  onSaved: () => void;
  onReload: () => void;
}) {
  const auth = useAuth()!;
  const users = useApi<User[]>("/api/auth/users");
  const [status, setStatus] = useState("");
  const [assignment, setAssignment] = useState("unchanged");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!note.trim()) {
      setError("Describe the evidence and your decision before saving.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await authenticatedMutation(
        `/api/dataops/monitoring/alerts/${encodeURIComponent(incident.id)}/actions`,
        auth.csrf_token,
        {
          expected_revision: incident.revision,
          note: note.trim(),
          ...(status ? { status } : {}),
          ...(assignment !== "unchanged" ? { assigned_to: assignment } : {}),
        },
      );
      setNote("");
      setStatus("");
      setAssignment("unchanged");
      onSaved();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Your decision could not be saved. Please retry.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <form
      className="incident-actions"
      onSubmit={submit}
      aria-label="Record investigation decision"
    >
      <div>
        <span className="eyebrow">INVESTIGATION DECISION</span>
        <h3>Move this incident forward</h3>
        <p>Your account and decision will be recorded in the audit timeline.</p>
      </div>
      <div className="incident-fields">
        <label>
          Next action
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            disabled={busy}
          >
            <option value="">Add note / update assignment</option>
            {(transitions[incident.status] || []).map((action) => (
              <option key={action.value} value={action.value}>
                {action.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Assign to
          <select
            value={assignment}
            onChange={(e) => setAssignment(e.target.value)}
            disabled={busy || !users.data}
          >
            <option value="unchanged">Keep current assignment</option>
            <option value="">Unassigned</option>
            {users.data?.map((user) => (
              <option key={user.id} value={user.id}>
                {user.display_name} ({user.username})
                {user.id === auth.user.id ? " · you" : ""}
              </option>
            ))}
          </select>
        </label>
      </div>
      {users.error && (
        <p role="alert">
          Unable to load assignments: {users.error}. You can still record a
          decision without changing ownership.
        </p>
      )}
      <label>
        Decision note
        <textarea
          required
          maxLength={2000}
          rows={4}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          disabled={busy}
          placeholder="What did you investigate? Record the evidence, outcome, and next steps."
          aria-describedby="decision-note-help"
        />
      </label>
      <p id="decision-note-help" className="caption">
        Required for every action. Do not include passwords, credentials, or
        patient information.
      </p>
      {error && (
        <div className="form-error" role="alert">
          <p>{error}</p>
          <button type="button" onClick={onReload} disabled={busy}>
            Reload latest incident
          </button>
        </div>
      )}
      <div className="incident-save">
        <span>
          Recording as <strong>{auth.user.display_name}</strong> · revision{" "}
          {incident.revision}
        </span>
        <button className="primary" type="submit" disabled={busy}>
          {busy ? "Saving decision…" : "Save decision"}
        </button>
      </div>
    </form>
  );
}
