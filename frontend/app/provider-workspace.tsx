"use client";

import { type FormEvent, useMemo, useState } from "react";
import {
  apiRequest,
  type ProviderCatalogEntry,
  type ProviderCredential,
} from "./api";

type FailureHandler = (caught: unknown, fallback: string) => void;

type CredentialDraft = {
  provider: string;
  name: string;
  apiKey: string;
  apiBase: string;
};

const emptyDraft: CredentialDraft = {
  provider: "groq",
  name: "",
  apiKey: "",
  apiBase: "",
};

export function ProviderWorkspace({
  token,
  catalog,
  credentials,
  onCredentialsChange,
  onFailure,
  onNotice,
}: {
  token: string;
  catalog: ProviderCatalogEntry[];
  credentials: ProviderCredential[];
  onCredentialsChange: (credentials: ProviderCredential[]) => void;
  onFailure: FailureHandler;
  onNotice: (message: string) => void;
}) {
  const [editing, setEditing] = useState<ProviderCredential | null>(null);
  const [draft, setDraft] = useState<CredentialDraft>(emptyDraft);
  const [showModal, setShowModal] = useState(false);
  const [testing, setTesting] = useState<ProviderCredential | null>(null);
  const [testModel, setTestModel] = useState("");
  const [saving, setSaving] = useState(false);

  const catalogBySlug = useMemo(
    () => new Map(catalog.map((provider) => [provider.slug, provider])),
    [catalog],
  );
  const selectedDefinition = catalogBySlug.get(draft.provider);

  function openCreate() {
    setEditing(null);
    setDraft({ ...emptyDraft, provider: catalog[0]?.slug ?? "groq" });
    setShowModal(true);
  }

  function openEdit(credential: ProviderCredential) {
    setEditing(credential);
    setDraft({
      provider: credential.provider,
      name: credential.name,
      apiKey: "",
      apiBase: credential.api_base ?? "",
    });
    setShowModal(true);
  }

  async function saveCredential(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    const payload: Record<string, string | null> = {
      name: draft.name.trim(),
      api_base: draft.apiBase.trim() || null,
    };
    if (!editing) payload.provider = draft.provider;
    if (draft.apiKey) payload.api_key = draft.apiKey;
    try {
      const saved = await apiRequest<ProviderCredential>(
        editing
          ? `/api/v1/provider-credentials/${editing.id}`
          : "/api/v1/provider-credentials",
        {
          method: editing ? "PATCH" : "POST",
          body: JSON.stringify(payload),
        },
        token,
      );
      onCredentialsChange(
        editing
          ? credentials.map((credential) =>
              credential.id === saved.id ? saved : credential,
            )
          : [...credentials, saved],
      );
      setDraft((current) => ({ ...current, apiKey: "" }));
      setShowModal(false);
      onNotice(editing ? "Provider credential updated." : "Provider credential saved securely.");
    } catch (caught) {
      onFailure(caught, "Could not save provider credential.");
    } finally {
      setSaving(false);
    }
  }

  async function deleteCredential(credential: ProviderCredential) {
    if (!window.confirm(`Delete credential “${credential.name}”?`)) return;
    setSaving(true);
    try {
      await apiRequest<void>(
        `/api/v1/provider-credentials/${credential.id}`,
        { method: "DELETE" },
        token,
      );
      onCredentialsChange(
        credentials.filter((entry) => entry.id !== credential.id),
      );
      onNotice("Provider credential deleted.");
    } catch (caught) {
      onFailure(caught, "Could not delete provider credential.");
    } finally {
      setSaving(false);
    }
  }

  function openTest(credential: ProviderCredential) {
    const definition = catalogBySlug.get(credential.provider);
    setTesting(credential);
    setTestModel(definition?.model_prefix ?? "");
  }

  async function testCredential(event: FormEvent) {
    event.preventDefault();
    if (!testing) return;
    setSaving(true);
    try {
      const checked = await apiRequest<{ status: ProviderCredential["status"]; checked_at: string }>(
        `/api/v1/provider-credentials/${testing.id}/test`,
        { method: "POST", body: JSON.stringify({ model: testModel.trim() }) },
        token,
      );
      onCredentialsChange(
        credentials.map((credential) =>
          credential.id === testing.id
            ? { ...credential, status: checked.status, last_checked_at: checked.checked_at }
            : credential,
        ),
      );
      setTesting(null);
      onNotice("Connection test succeeded.");
    } catch (caught) {
      onCredentialsChange(
        credentials.map((credential) =>
          credential.id === testing.id
            ? { ...credential, status: "invalid", last_checked_at: new Date().toISOString() }
            : credential,
        ),
      );
      onFailure(caught, "Provider connection test failed.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <section className="section-intro panel provider-intro">
        <div>
          <span className="panel-kicker">BRING YOUR OWN KEY</span>
          <h2>AI provider credentials</h2>
          <p>
            Connect Groq, Claude, Gemini, OpenAI, OpenRouter, or any compatible
            endpoint. Keys are encrypted before they reach the database.
          </p>
        </div>
        <button className="primary-button" onClick={openCreate} type="button">
          ＋ Add provider
        </button>
      </section>

      <section className="provider-summary" aria-label="Provider credential summary">
        <article className="panel"><span>CONNECTED</span><strong>{credentials.filter((credential) => credential.status === "connected").length}</strong><small>Verified credentials</small></article>
        <article className="panel"><span>PROVIDERS</span><strong>{new Set(credentials.map((credential) => credential.provider)).size}</strong><small>Configured services</small></article>
        <article className="panel"><span>STORED KEYS</span><strong>{credentials.length}</strong><small>Encrypted at rest</small></article>
      </section>

      {credentials.length ? (
        <section className="provider-grid">
          {credentials.map((credential) => {
            const definition = catalogBySlug.get(credential.provider);
            return (
              <article className="panel provider-card" key={credential.id}>
                <div className="provider-card-head">
                  <span className="provider-logo">{(definition?.label ?? credential.provider).slice(0, 1)}</span>
                  <span className={`credential-status credential-${credential.status}`}>{credential.status}</span>
                </div>
                <span className="panel-kicker">{definition?.label ?? credential.provider}</span>
                <h3>{credential.name}</h3>
                <code>{credential.key_hint}</code>
                {credential.api_base && <small className="provider-base">{credential.api_base}</small>}
                <div className="provider-card-meta">
                  <span>Last used</span>
                  <strong>{credential.last_used_at ? new Date(credential.last_used_at).toLocaleString() : "Never"}</strong>
                </div>
                <div className="variant-actions">
                  <button className="secondary-button" onClick={() => openTest(credential)} type="button">Test</button>
                  <button className="secondary-button" onClick={() => openEdit(credential)} type="button">Edit</button>
                  <button className="danger-button" disabled={saving} onClick={() => void deleteCredential(credential)} type="button">Delete</button>
                </div>
              </article>
            );
          })}
        </section>
      ) : (
        <section className="panel stage-empty">
          <span>⌁</span>
          <h2>No provider credentials yet</h2>
          <p>Add a personal API key before attaching it to a model variant.</p>
          <button className="primary-button" onClick={openCreate} type="button">＋ Connect first provider</button>
        </section>
      )}

      {showModal && (
        <ProviderDialog titleId="provider-dialog-title" onClose={() => setShowModal(false)}>
          <span className="panel-kicker">SECURE CREDENTIAL</span>
          <h2 id="provider-dialog-title">{editing ? "Update provider" : "Connect a provider"}</h2>
          <p>The complete API key is accepted once and is never shown again.</p>
          <form onSubmit={saveCredential}>
            <div className="form-grid">
              <label>
                Provider
                <select disabled={!!editing} value={draft.provider} onChange={(event) => setDraft((current) => ({ ...current, provider: event.target.value, apiBase: "" }))}>
                  {catalog.map((provider) => <option key={provider.slug} value={provider.slug}>{provider.label}</option>)}
                </select>
              </label>
              <label>
                Credential name
                <input maxLength={200} required value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} placeholder="Personal account" />
              </label>
            </div>
            <label>
              API key {editing && <small>leave blank to keep the current key</small>}
              <input autoComplete="off" required={!editing} type="password" value={draft.apiKey} onChange={(event) => setDraft((current) => ({ ...current, apiKey: event.target.value }))} placeholder={selectedDefinition?.api_key_placeholder ?? "API key"} />
            </label>
            {(selectedDefinition?.supports_custom_base_url || draft.apiBase) && (
              <label>
                API base URL
                <input required={selectedDefinition?.supports_custom_base_url} type="url" value={draft.apiBase} onChange={(event) => setDraft((current) => ({ ...current, apiBase: event.target.value }))} placeholder="http://localhost:11434/v1" />
              </label>
            )}
            <div className="credential-safety-note"><span>✓</span><p><strong>Encrypted storage</strong><br />The key is encrypted server-side and excluded from API responses, logs, traces, and worker messages.</p></div>
            <ProviderDialogActions label={editing ? "Save changes" : "Save credential"} onCancel={() => setShowModal(false)} saving={saving} />
          </form>
        </ProviderDialog>
      )}

      {testing && (
        <ProviderDialog titleId="provider-test-title" onClose={() => setTesting(null)}>
          <span className="panel-kicker">LIVE CONNECTION TEST</span>
          <h2 id="provider-test-title">Test {testing.name}</h2>
          <p>This sends one minimal prompt to the selected model and may consume a small number of tokens.</p>
          <form onSubmit={testCredential}>
            <label>
              Model ID
              <input maxLength={300} required value={testModel} onChange={(event) => setTestModel(event.target.value)} placeholder="anthropic/your-model-id" />
            </label>
            <ProviderDialogActions label="Run connection test" onCancel={() => setTesting(null)} saving={saving} />
          </form>
        </ProviderDialog>
      )}
    </>
  );
}

function ProviderDialog({ children, onClose, titleId }: { children: React.ReactNode; onClose: () => void; titleId: string }) {
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section className="modal modal-wide" role="dialog" aria-modal="true" aria-labelledby={titleId}><button className="modal-close" onClick={onClose} aria-label="Close dialog" type="button">×</button>{children}</section></div>;
}

function ProviderDialogActions({ label, onCancel, saving }: { label: string; onCancel: () => void; saving: boolean }) {
  return <div className="modal-actions"><button className="secondary-button" onClick={onCancel} type="button">Cancel</button><button className="primary-button" disabled={saving} type="submit">{saving ? "Please wait…" : label}</button></div>;
}
