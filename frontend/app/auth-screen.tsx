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
    <main className="auth-shell auth-shell-v2">
      <header className="auth-global-header">
        <div className="brand">
          <span className="brand-mark">E</span>
          <span>Evalflow</span>
          <code>v0.37</code>
        </div>
        <div className="auth-environment">
          <span>SELF-HOSTED</span>
          <span className="environment-ready"><i /> SYSTEM READY</span>
        </div>
      </header>

      <div className="auth-stage">
        <section className="auth-context" aria-label="Product workflow">
          <span className="eyebrow">LLM EVALUATION WORKSPACE</span>
          <h1>
            Evaluate models.
            <span>Ship with evidence.</span>
          </h1>
          <p>
            Run the same benchmark against real providers and inspect quality,
            latency, cost, and failures in one reproducible workflow.
          </p>

          <ol className="auth-workflow">
            <li>
              <code>01</code>
              <span><strong>Dataset</strong><small>Import deterministic test cases</small></span>
            </li>
            <li>
              <code>02</code>
              <span><strong>Variants</strong><small>Configure provider-backed models</small></span>
            </li>
            <li>
              <code>03</code>
              <span><strong>Evaluation</strong><small>Execute with bounded concurrency</small></span>
            </li>
            <li>
              <code>04</code>
              <span><strong>Compare</strong><small>Review quality, latency, tokens, and cost</small></span>
            </li>
          </ol>

          <div className="auth-signal-row" aria-label="Platform capabilities">
            <span><b>14+</b> providers</span>
            <span><b>3</b> quality metrics</span>
            <span><b>100%</b> network-free tests</span>
          </div>
        </section>

        <section className="auth-access-card">
          <header className="auth-card-header">
            <div>
              <span className="auth-card-kicker">WORKSPACE ACCESS</span>
              <h2>{headings[mode]}</h2>
            </div>
            <code>evalflow.local</code>
          </header>
          <p className="auth-card-copy">
            {mode === "login"
              ? "Continue to experiments, datasets, model configs, and evaluation runs."
              : mode === "register"
                ? "Create an isolated workspace for your datasets, credentials, and runs."
                : mode === "forgot"
                  ? "We will send a one-time recovery link to your verified email."
                  : "Choose a new password to secure your workspace."}
          </p>
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
          <footer className="auth-card-footer">
            <span>ENCRYPTED BYOK</span>
            <span>HTTPONLY SESSIONS</span>
            <span>RATE LIMITED</span>
          </footer>
        </section>
      </div>

      <footer className="auth-global-footer">
        <span>FastAPI · PostgreSQL · Redis · Celery · React</span>
        <span>LOCAL EVALUATION INFRASTRUCTURE</span>
      </footer>
    </main>
  );
}
