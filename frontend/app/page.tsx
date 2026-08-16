"use client";

import { type FormEvent, useEffect, useState } from "react";
import { apiRequest, type TokenResponse, type User } from "./api";
import Dashboard from "./dashboard";

const TOKEN_KEY = "llm-eval-access-token";

function AuthScreen({
  onAuthenticated,
}: {
  onAuthenticated: (token: string) => void;
}) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      if (mode === "register") {
        await apiRequest<User>("/api/v1/auth/register", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
      }
      const response = await apiRequest<TokenResponse>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      onAuthenticated(response.access_token);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Authentication failed.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  function changeMode(nextMode: "login" | "register") {
    setMode(nextMode);
    setError("");
  }

  return (
    <main className="auth-shell">
      <section className="auth-form-panel">
        <div className="brand">
          <span className="brand-mark">E</span>
          <span>Evalflow</span>
        </div>
        <div className="auth-copy">
          <span className="eyebrow">LLM EVALUATION WORKSPACE</span>
          <h1>{mode === "login" ? "Welcome back" : "Create your workspace"}</h1>
          <p>Compare real models, understand every tradeoff, and ship with evidence.</p>
        </div>
        <div className="auth-tabs" role="tablist" aria-label="Authentication mode">
          <button className={mode === "login" ? "active" : ""} onClick={() => changeMode("login")} type="button">Sign in</button>
          <button className={mode === "register" ? "active" : ""} onClick={() => changeMode("register")} type="button">Create account</button>
        </div>
        <form className="auth-form" onSubmit={submit}>
          <label>
            Email address
            <input autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@company.com" type="email" required />
          </label>
          <label>
            Password
            <input autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 8 characters" minLength={8} type="password" required />
          </label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="primary-button auth-submit" disabled={submitting} type="submit">
            {submitting ? "Please wait…" : mode === "login" ? "Sign in to Evalflow" : "Create account"}
          </button>
        </form>
        <p className="auth-footnote">Protected by expiring JWT access tokens. Your model API keys stay on the server.</p>
      </section>

      <section className="auth-visual" aria-label="Product preview">
        <div className="glow glow-one" />
        <div className="glow glow-two" />
        <div className="preview-window">
          <div className="preview-top"><div><span className="preview-kicker">LATEST COMPARISON</span><h2>Qwen vs GPT-OSS</h2></div><span className="live-pill"><i /> Completed</span></div>
          <div className="preview-metrics"><div><span>QUALITY</span><strong>91.4%</strong><small className="positive">+4.8%</small></div><div><span>AVG LATENCY</span><strong>1.28s</strong><small className="positive">−320ms</small></div><div><span>TOTAL TOKENS</span><strong>8.2k</strong><small>10 requests</small></div></div>
          <div className="chart-card"><div className="chart-head"><span>Evaluation score</span><span className="chart-legend"><i /> Qwen <i /> GPT-OSS</span></div><div className="bar-chart" aria-hidden="true">{[74, 88, 68, 92, 81, 96, 76].map((height, index) => <div className="bar-group" key={height + index}><span style={{ height: `${height}%` }} /><span style={{ height: `${Math.max(30, height - 14 + (index % 3) * 7)}%` }} /></div>)}</div></div>
          <div className="preview-table"><span>Model</span><span>Exact match</span><span>Latency</span><strong>Qwen 3.6 27B</strong><span className="positive">0.94</span><span>1.12s</span><strong>GPT-OSS 20B</strong><span>0.86</span><span>1.44s</span></div>
        </div>
      </section>
    </main>
  );
}

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setToken(sessionStorage.getItem(TOKEN_KEY));
      setReady(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  function authenticated(nextToken: string) {
    sessionStorage.setItem(TOKEN_KEY, nextToken);
    setToken(nextToken);
  }

  function logout() {
    sessionStorage.removeItem(TOKEN_KEY);
    setToken(null);
  }

  if (!ready) return <AuthScreen onAuthenticated={authenticated} />;
  return token ? <Dashboard token={token} onLogout={logout} /> : <AuthScreen onAuthenticated={authenticated} />;
}
