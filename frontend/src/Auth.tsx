import { createContext, useContext, useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Activity, LogOut, ShieldCheck } from "lucide-react";
import Administration from "./Administration";

export type User = {
  id: string;
  username: string;
  display_name: string;
  role: "administrator" | "analyst" | "viewer";
};
type Session = { user: User; csrf_token: string };
type Auth = Session & { logout: () => Promise<void> };
export const AuthContext = createContext<Auth | null>(null);
export const useAuth = () => useContext(AuthContext);
export const SESSION_EXPIRED = "carerank:session-expired";

export async function authenticatedMutation(
  url: string,
  csrf: string,
  body?: unknown,
  method: "POST" | "PATCH" = "POST",
) {
  const response = await fetch(url, {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (response.status === 401 && url !== "/api/auth/login")
    window.dispatchEvent(new Event(SESSION_EXPIRED));
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(
      response.status === 409 && url.includes("/alerts/")
        ? "This incident changed while you were reviewing it. Reload the latest revision before saving your decision."
        : response.status === 429
          ? "Too many attempts. Please wait before trying again."
          : typeof payload.detail === "string"
            ? payload.detail
            : `Your request could not be completed (${response.status}).`,
    );
  }
  return response.status === 204 ? null : response.json();
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expired, setExpired] = useState(false);
  const [retry, setRetry] = useState(0);
  const [administration, setAdministration] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    fetch("/api/auth/me", {
      credentials: "same-origin",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (response.status === 401) return null;
        if (!response.ok)
          throw new Error(
            "The sign-in service is unavailable. Please try again.",
          );
        return response.json();
      })
      .then((value) => {
        if (!controller.signal.aborted) setSession(value);
      })
      .catch((cause) => {
        if (!controller.signal.aborted) setError(cause.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    const expire = () => {
      setSession(null);
      setExpired(true);
      setAdministration(false);
    };
    window.addEventListener(SESSION_EXPIRED, expire);
    return () => {
      controller.abort();
      window.removeEventListener(SESSION_EXPIRED, expire);
    };
  }, [retry]);
  const logout = async () => {
    if (!session) return;
    await authenticatedMutation("/api/auth/logout", session.csrf_token);
    setSession(null);
    setExpired(false);
    setAdministration(false);
  };
  if (loading)
    return (
      <div className="auth-loading" role="status">
        Checking your session…
      </div>
    );
  if (error)
    return (
      <main className="auth-page">
        <section className="auth-card">
          <h1>Unable to connect</h1>
          <p role="alert">{error}</p>
          <button onClick={() => setRetry((n) => n + 1)}>Try again</button>
        </section>
      </main>
    );
  if (!session)
    return (
      <Login
        expired={expired}
        onLogin={(value) => {
          setSession(value);
          setExpired(false);
        }}
      />
    );
  return (
    <AuthContext.Provider value={{ ...session, logout }}>
      <SessionBar
        administration={administration}
        onAdministration={() => setAdministration((value) => !value)}
      />
      {administration && session.user.role === "administrator" ? (
        <Administration />
      ) : (
        children
      )}
    </AuthContext.Provider>
  );
}

function SessionBar({
  administration,
  onAdministration,
}: {
  administration: boolean;
  onAdministration: () => void;
}) {
  const auth = useAuth()!;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <header className="session-bar" aria-label="Signed-in account">
      <div>
        <ShieldCheck size={17} aria-hidden="true" />
        <span>Secure analyst workspace</span>
      </div>
      <div className="session-account">
        {auth.user.role === "administrator" && (
          <button onClick={onAdministration} aria-pressed={administration}>
            {administration ? "Back to workspace" : "Administration"}
          </button>
        )}
        <span>
          <strong>{auth.user.display_name}</strong>
          <small>{auth.user.role}</small>
        </span>
        <button
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              await auth.logout();
            } catch (cause) {
              setError(
                cause instanceof Error
                  ? cause.message
                  : "Sign out failed. Please retry.",
              );
            } finally {
              setBusy(false);
            }
          }}
        >
          <LogOut size={15} aria-hidden="true" />
          {busy ? "Signing out…" : "Sign out"}
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
    </header>
  );
}

function Login({
  expired,
  onLogin,
}: {
  expired: boolean;
  onLogin: (session: Session) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await authenticatedMutation("/api/auth/login", "", {
        username,
        password,
      });
      onLogin(result);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Sign in failed. Please retry.",
      );
    } finally {
      setPassword("");
      setBusy(false);
    }
  }
  return (
    <main className="auth-page">
      <section className="auth-intro">
        <span className="auth-brand">
          <Activity aria-hidden="true" /> CareRank <small>4.0</small>
        </span>
        <span className="eyebrow">DATA RELIABILITY & ANALYST OPERATIONS</span>
        <h1>
          Evidence to decisions.
          <br />
          Every action accountable.
        </h1>
        <p>
          Investigate data-quality incidents, coordinate ownership, and follow
          the complete decision history in one secure workspace.
        </p>
        <div className="auth-assurances">
          <ShieldCheck aria-hidden="true" />
          <span>
            Role-based access · Authenticated decisions · Preserved history
          </span>
        </div>
        <p className="caption">
          Educational provider intelligence. No patient records or clinical
          ratings.
        </p>
      </section>
      <section className="auth-card" aria-labelledby="sign-in-title">
        <span className="eyebrow">WELCOME BACK</span>
        <h2 id="sign-in-title">Sign in to CareRank</h2>
        <p>Use your provisioned workspace account.</p>
        {expired && (
          <p className="auth-notice" role="status">
            Your session expired. Sign in again to continue.
          </p>
        )}
        <form onSubmit={submit}>
          <label>
            Username
            <input
              autoComplete="username"
              name="username"
              required
              maxLength={80}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
            />
          </label>
          <label>
            Password
            <input
              autoComplete="current-password"
              name="password"
              type="password"
              required
              maxLength={256}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <button className="primary" disabled={busy} type="submit">
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="caption">
          Need access? Contact your workspace administrator.
        </p>
      </section>
    </main>
  );
}
