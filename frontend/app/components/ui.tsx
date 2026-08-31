"use client";

import type { ReactNode } from "react";

import type { EvaluationRun } from "../api";

export function StatusBadge({
  status,
}: {
  status: EvaluationRun["status"];
}) {
  return <span className={`status status-${status}`}>{status}</span>;
}

export function LoadingState({ label }: { label: string }) {
  return (
    <div className="dashboard-loading" role="status">
      <span className="loading-skeleton" />
      <p>{label}</p>
    </div>
  );
}

export function Dialog({
  children,
  onClose,
  titleId,
  wide = false,
}: {
  children: ReactNode;
  onClose: () => void;
  titleId: string;
  wide?: boolean;
}) {
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      role="presentation"
    >
      <section
        aria-labelledby={titleId}
        aria-modal="true"
        className={`modal${wide ? " modal-wide" : ""}`}
        role="dialog"
      >
        <button
          aria-label="Close dialog"
          className="modal-close"
          onClick={onClose}
          type="button"
        >
          ×
        </button>
        {children}
      </section>
    </div>
  );
}

export function DialogActions({
  disabled = false,
  label,
  onCancel,
  saving,
}: {
  disabled?: boolean;
  label: string;
  onCancel: () => void;
  saving: boolean;
}) {
  return (
    <div className="modal-actions">
      <button className="secondary-button" onClick={onCancel} type="button">
        Cancel
      </button>
      <button
        className="primary-button"
        disabled={disabled || saving}
        type="submit"
      >
        {saving ? "Saving…" : label}
      </button>
    </div>
  );
}
