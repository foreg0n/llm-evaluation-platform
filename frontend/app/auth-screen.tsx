"use client";

import { type FormEvent, useEffect, useState } from "react";
import {
  ApiError,
  apiRequest,
  setApiAccessToken,
  type TokenResponse,
  type User,
} from "./api";

type AuthMode = "login" | "register" | "forgot" | "reset";

const headings: Record<AuthMode, string> = {
  login: "Welcome back",
  register: "Create your workspace",
  forgot: "Reset your password",
  reset: "Choose a new password",
};

function clearAccountActionFragment() {
  window.history.replaceState(
    {},
    "",
    `${window.location.pathname}${window.location.search}`,
  );
}

export default function AuthScreen({
  onAuthenticated,
}: {
  onAuthenticated: (token: string) => void;
}) {
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [resetToken, setResetToken] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [needsVerification, setNeedsVerification] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.slice(1));
    const action = params.get("action");
    const token = params.get("token");
    if (!token) return;
    clearAccountActionFragment();
    if (action === "reset-password") {
      queueMicrotask(() => {
        setResetToken(token);
        setMode("reset");
      });
      return;
    }
    if (action !== "verify-email") return;
    void apiRequest<{ message: string }>(
      "/api/v1/auth/email-verification/confirm",
      { method: "POST", body: JSON.stringify({ token }) },
    )
      .then((result) => {
        setNotice(result.message);
        setMode("login");
      })
      .catch((caught) => {
        setError(
          caught instanceof Error
            ? caught.message
            : "The verification link is invalid or expired.",
        );
      })
      .finally(() => setSubmitting(false));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    setNeedsVerification(false);
    setSubmitting(true);
    try {
      if (mode === "register") {
        await apiRequest<User>("/api/v1/auth/register", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
        setMode("login");
        setPassword("");
        setNotice("Account created. Check your email to verify it before signing in.");
        return;
      }
      if (mode === "forgot") {
        const result = await apiRequest<{ message: string }>(
          "/api/v1/auth/password-reset/request",
          { method: "POST", body: JSON.stringify({ email }) },
        );
        setMode("login");
        setNotice(result.message);
        return;
      }
      if (mode === "reset") {
        if (password !== passwordConfirmation) {
          throw new Error("Passwords do not match.");
        }
        const result = await apiRequest<{ message: string }>(
          "/api/v1/auth/password-reset/confirm",
          {
            method: "POST",
            body: JSON.stringify({ token: resetToken, new_password: password }),
          },
        );
        setMode("login");
        setPassword("");
        setPasswordConfirmation("");
        setResetToken("");
        setNotice(result.message);
        return;
      }
      const response = await apiRequest<TokenResponse>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setApiAccessToken(response.access_token);
      onAuthenticated(response.access_token);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 403) {
        setNeedsVerification(true);
      }
      setError(
        caught instanceof Error ? caught.message : "Authentication failed.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function resendVerification() {
    setError("");
    setSubmitting(true);
    try {
      const result = await apiRequest<{ message: string }>(
        "/api/v1/auth/email-verification/request",
        { method: "POST", body: JSON.stringify({ email }) },
      );
      setNeedsVerification(false);
      setNotice(result.message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Request failed.");
    } finally {
      setSubmitting(false);
    }
  }

  function changeMode(nextMode: AuthMode) {
    setMode(nextMode);
    setError("");
    setNotice("");
    setNeedsVerification(false);
  }

  const requestsEmail = mode !== "reset";
  const requestsPassword = mode === "login" || mode === "register" || mode === "reset";

  return (
    <main className="auth-shell">
      <section className="auth-form-panel">
        <div className="brand"><span className="brand-mark">E</span><span>Evalflow</span></div>
        <div className="auth-copy">
          <span className="eyebrow">LLM EVALUATION WORKSPACE</span>
          <h1>{headings[mode]}</h1>
          <p>Compare real models, understand every tradeoff, and ship with evidence.</p>
        </div>
        {(mode === "login" || mode === "register") && (
          <div className="auth-tabs" role="tablist" aria-label="Authentication mode">
            <button className={mode === "login" ? "active" : ""} onClick={() => changeMode("login")} type="button">Sign in</button>
            <button className={mode === "register" ? "active" : ""} onClick={() => changeMode("register")} type="button">Create account</button>
          </div>
        )}
        <form className="auth-form" onSubmit={submit}>
          {requestsEmail && (
            <label>Email address<input autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@company.com" type="email" required /></label>
          )}
          {requestsPassword && (
            <label>{mode === "reset" ? "New password" : "Password"}<input autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 8 characters" minLength={8} type="password" required /></label>
          )}
          {mode === "reset" && (
            <label>Confirm new password<input autoComplete="new-password" value={passwordConfirmation} onChange={(event) => setPasswordConfirmation(event.target.value)} placeholder="Repeat your new password" minLength={8} type="password" required /></label>
          )}
          {notice && <p className="form-notice" role="status">{notice}</p>}
          {error && <p className="form-error" role="alert">{error}</p>}
          {needsVerification && <button className="auth-link" disabled={submitting} onClick={resendVerification} type="button">Resend verification email</button>}
          <button className="primary-button auth-submit" disabled={submitting} type="submit">
            {submitting ? "Please wait…" : mode === "login" ? "Sign in to Evalflow" : mode === "register" ? "Create account" : mode === "forgot" ? "Send reset link" : "Update password"}
          </button>
          {mode === "login" ? (
            <button className="auth-link" onClick={() => changeMode("forgot")} type="button">Forgot password?</button>
          ) : (mode === "forgot" || mode === "reset") ? (
            <button className="auth-link" onClick={() => changeMode("login")} type="button">Back to sign in</button>
          ) : null}
        </form>
        <p className="auth-footnote">Protected by verified email, one-time recovery links, short-lived access tokens, and rotating HttpOnly refresh sessions.</p>
      </section>
      <section className="auth-visual" aria-label="Product preview">
        <div className="glow glow-one" /><div className="glow glow-two" />
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
