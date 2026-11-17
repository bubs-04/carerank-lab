import { useState } from "react";
import { authenticatedMutation, AuthMutationError, useAuth } from "./Auth";
import type { User } from "./Auth";
import { useApi } from "./api";

type Account = User & { active: boolean; revision: number };
type Audit = {
  id: string;
  actor_user_id: string | null;
  subject_user_id: string | null;
  action: string;
  details: Record<string, unknown>;
  created_at: string;
};

export default function Administration() {
  const [refresh, setRefresh] = useState(0);
  const [conflict, setConflict] = useState("");
  const users = useApi<Account[]>("/api/auth/admin/users", refresh);
  const events = useApi<Audit[]>("/api/auth/admin/events", refresh);
  const name = (id: string | null) =>
    users.data?.find((u) => u.id === id)?.display_name || id || "System";
  return (
    <main className="admin-workspace">
      <span className="eyebrow">WORKSPACE ADMINISTRATION</span>
      <h1>Access and accountability</h1>
      <p>
        Manage provisioned accounts and review the latest security events. Role
        and access changes revoke the affected account’s sessions.
      </p>
      <section className="panel">
        <h2>Workspace accounts</h2>
        {conflict && (
          <p role="alert">
            {conflict} Review the latest account settings before trying again.
          </p>
        )}
        <p>
          Provisioning is restricted to the development command line. At least
          one active Administrator must remain.
        </p>
        {users.error ? (
          <p role="alert">{users.error}</p>
        ) : !users.data ? (
          <p role="status">Loading accounts…</p>
        ) : (
          <div className="account-list">
            {users.data.map((account) => (
              <AccountForm
                key={`${account.id}-${account.revision}-${refresh}`}
                account={account}
                onSaved={() => {
                  setConflict("");
                  setRefresh((n) => n + 1);
                }}
                onConflict={(message) => {
                  setConflict(message);
                  setRefresh((n) => n + 1);
                }}
              />
            ))}
          </div>
        )}
      </section>
      <section className="panel">
        <h2>Security audit</h2>
        <p>
          Latest 100 recorded events. Credentials and session tokens are
          excluded.
        </p>
        {events.error ? (
          <p role="alert">{events.error}</p>
        ) : !events.data ? (
          <p role="status">Loading security events…</p>
        ) : (
          <ol className="monitor-timeline">
            {events.data.map((event) => (
              <li key={event.id}>
                <strong>{event.action.replaceAll("_", " ")}</strong>
                <p>
                  {name(event.actor_user_id)}
                  {event.subject_user_id &&
                    ` · Account: ${name(event.subject_user_id)}`}
                </p>
                <small>{new Date(event.created_at).toLocaleString()}</small>
                {Object.keys(event.details).length > 0 && (
                  <details>
                    <summary>Recorded changes</summary>
                    <pre className="dataops-code">
                      {JSON.stringify(event.details, null, 2)}
                    </pre>
                  </details>
                )}
              </li>
            ))}
          </ol>
        )}
      </section>
    </main>
  );
}

function AccountForm({
  account,
  onSaved,
  onConflict,
}: {
  account: Account;
  onSaved: () => void;
  onConflict: (message: string) => void;
}) {
  const auth = useAuth()!;
  const [role, setRole] = useState(account.role);
  const [active, setActive] = useState(account.active);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <form
      className="account-form"
      aria-label={`Manage ${account.username}`}
      onSubmit={async (event) => {
        event.preventDefault();
        setBusy(true);
        setError("");
        try {
          await authenticatedMutation(
            `/api/auth/users/${encodeURIComponent(account.id)}`,
            auth.csrf_token,
            {
              expected_revision: account.revision,
              ...(role !== account.role ? { role } : {}),
              ...(active !== account.active ? { active } : {}),
            },
            "PATCH",
          );
          if (account.id === auth.user.id)
            window.dispatchEvent(new Event("carerank:session-expired"));
          else onSaved();
        } catch (cause) {
          if (cause instanceof AuthMutationError && cause.status === 409) {
            onConflict(cause.message);
            return;
          }
          setError(
            cause instanceof Error ? cause.message : "Account update failed.",
          );
        } finally {
          setBusy(false);
        }
      }}
    >
      <div>
        <strong>{account.display_name}</strong>
        <p>
          {account.username}
          {account.id === auth.user.id ? " · You" : ""}
        </p>
      </div>
      <label>
        Role
        <select
          aria-label={`Role for ${account.username}`}
          value={role}
          onChange={(e) => setRole(e.target.value as User["role"])}
          disabled={busy}
        >
          <option value="administrator">Administrator</option>
          <option value="analyst">Analyst</option>
          <option value="viewer">Viewer</option>
        </select>
      </label>
      <label className="active-account">
        <input
          type="checkbox"
          checked={active}
          onChange={(e) => setActive(e.target.checked)}
          disabled={busy}
          aria-label={`Active account ${account.username}`}
        />{" "}
        Active
      </label>
      <button
        type="submit"
        disabled={busy || (role === account.role && active === account.active)}
      >
        {busy ? "Saving…" : "Update access"}
      </button>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
