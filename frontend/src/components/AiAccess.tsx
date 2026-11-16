import { useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import { useNavigate } from "react-router-dom";
import { fetchAiConfig, getAiSession, refreshAiUsage, signInAi, signOutAi, subscribeAiSession } from "../api/aiAccess";

interface GoogleIdentity {
  initialize(options: { client_id: string; callback: (response: { credential: string }) => void; auto_select: boolean }): void;
  renderButton(element: HTMLElement, options: { theme: string; size: string; width: number }): void;
  disableAutoSelect(): void;
}
declare global {
  interface Window { google?: { accounts: { id: GoogleIdentity } } }
}

let library: Promise<GoogleIdentity> | undefined;
function loadGoogle() {
  if (window.google) return Promise.resolve(window.google.accounts.id);
  if (!library) {
    library = new Promise<GoogleIdentity>((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.onload = () => window.google ? resolve(window.google.accounts.id) : reject(new Error("Google sign-in did not load."));
      script.onerror = () => { script.remove(); library = undefined; reject(new Error("Could not load Google sign-in.")); };
      document.head.appendChild(script);
    });
  }
  return library;
}

export default function AiAccess({ label = "AI access", className = "", redirectTo }: {
  label?: string; className?: string; redirectTo?: string;
}) {
  const navigate = useNavigate();
  const titleId = useId();
  const session = useSyncExternalStore(subscribeAiSession, getAiSession);
  const signedIn = !!session;
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const target = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    if (!open) return;
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    if (signedIn) { void refreshAiUsage(); return; }
    fetchAiConfig().then(async (config) => {
      if (cancelled) return;
      if (!config.configured) throw new Error("AI sign-in has not been configured yet.");
      const google = await loadGoogle();
      if (cancelled || !target.current) return;
      google.initialize({ client_id: config.client_id, auto_select: false, callback: (response) => {
        if (cancelled) return;
        setLoading(true);
        setError("");
        signInAi(response.credential)
          .then(() => { if (redirectTo) navigate(redirectTo); })
          .catch((err) => setError(err instanceof Error ? err.message : "Sign-in failed."))
          .finally(() => setLoading(false));
      } });
      target.current.replaceChildren();
      google.renderButton(target.current, { theme: "outline", size: "large", width: 250 });
    }).catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : "Sign-in unavailable."); });
    return () => { cancelled = true; };
  }, [open, signedIn, navigate, redirectTo]);

  return <>
    <button type="button" className={`ai-access-button ${className}`} onClick={() => { setError(""); setOpen(true); }}>
      {session ? `AI ${session.usage.your_daily_requests}/${session.usage.limits.per_user_daily}` : label}
    </button>
    {open && <dialog ref={dialog} className="ai-access-dialog" aria-labelledby={titleId} onCancel={() => setOpen(false)}>
      <h2 id={titleId}>AI access</h2>
      {session ? <>
        <p className="ai-access-email">{session.user.email}</p>
        <dl>
          <dt>Your requests today</dt><dd>{session.usage.your_daily_requests} / {session.usage.limits.per_user_daily}</dd>
          <dt>Your requests this month</dt><dd>{session.usage.your_monthly_requests} / {session.usage.limits.per_user_monthly}</dd>
          <dt>Shared daily budget</dt><dd>{session.usage.daily_requests} / {session.usage.limits.daily}</dd>
          <dt>Shared monthly budget</dt><dd>{session.usage.monthly_requests} / {session.usage.limits.monthly}</dd>
          <dt>Your reported tokens this month</dt><dd>{session.usage.your_reported_total_tokens.toLocaleString()}</dd>
        </dl>
        <p className="ai-access-note">Resets at midnight UTC. Request allowances are not dollar limits.</p>
        <button type="button" className="ai-access-button" onClick={() => {
          signOutAi(); window.google?.accounts.id.disableAutoSelect();
        }}>Sign out</button>
      </> : <>
        <p>Dacey &amp; Market Context</p>
        <div ref={target} style={{ minHeight: 44 }} />
        {loading && <p role="status">Verifying sign-in...</p>}
      </>}
      {error && <p role="alert">{error}</p>}
      <button type="button" className="ai-access-button" onClick={() => setOpen(false)}>Close</button>
    </dialog>}
  </>;
}
