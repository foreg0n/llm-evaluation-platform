"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  apiRequest,
  type Dataset,
  type DatasetImportResponse,
  type DatasetItem,
  type EvaluationRun,
  type ModelVariant,
  type Project,
  type User,
} from "./api";
import { ModelWorkspace, RunWorkspace } from "./evaluation-workspace";

const shortId = (value: string) => value.slice(0, 8);
const formatDate = (value: string) =>
  new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));

function StatusBadge({ status }: { status: EvaluationRun["status"] }) {
  return <span className={`status status-${status}`}>{status}</span>;
}

type DatasetDraft = { name: string; description: string };
type ItemDraft = {
  externalId: string;
  input: string;
  expectedOutput: string;
  keywords: string;
};

const emptyDatasetDraft: DatasetDraft = { name: "", description: "" };
const emptyItemDraft: ItemDraft = {
  externalId: "",
  input: "",
  expectedOutput: "",
  keywords: "",
};

export default function Dashboard({
  token,
  onLogout,
}: {
  token: string;
  onLogout: () => void;
}) {
  const [user, setUser] = useState<User | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [runs, setRuns] = useState<EvaluationRun[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [variants, setVariants] = useState<ModelVariant[]>([]);
  const [items, setItems] = useState<DatasetItem[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [selectedDataset, setSelectedDataset] = useState<Dataset | null>(null);
  const [projectSection, setProjectSection] = useState<"datasets" | "models" | "runs">("datasets");
  const [loading, setLoading] = useState(true);
  const [loadingProject, setLoadingProject] = useState(false);
  const [loadingItems, setLoadingItems] = useState(false);
  const [error, setError] = useState("");
  const [showProjectModal, setShowProjectModal] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [projectDescription, setProjectDescription] = useState("");
  const [datasetModal, setDatasetModal] = useState<"create" | "edit" | null>(
    null,
  );
  const [datasetDraft, setDatasetDraft] =
    useState<DatasetDraft>(emptyDatasetDraft);
  const [itemModal, setItemModal] = useState<"create" | "edit" | null>(null);
  const [editingItem, setEditingItem] = useState<DatasetItem | null>(null);
  const [itemDraft, setItemDraft] = useState<ItemDraft>(emptyItemDraft);
  const [showImportModal, setShowImportModal] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importName, setImportName] = useState("");
  const [importDescription, setImportDescription] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);

  const handleFailure = useCallback((caught: unknown, fallback: string) => {
    if (caught instanceof ApiError && caught.status === 401) {
      onLogout();
      return;
    }
    setError(caught instanceof Error ? caught.message : fallback);
  }, [onLogout]);

  const upsertRun = useCallback((nextRun: EvaluationRun) => {
    setRuns((current) => [nextRun, ...current.filter((run) => run.id !== nextRun.id)]);
  }, []);

  async function loadWorkspace() {
    try {
      const [account, projectList, runList] = await Promise.all([
        apiRequest<User>("/api/v1/auth/me", {}, token),
        apiRequest<Project[]>("/api/v1/projects", {}, token),
        apiRequest<EvaluationRun[]>("/api/v1/runs", {}, token),
      ]);
      setUser(account);
      setProjects(projectList);
      setRuns(runList);
      setError("");
    } catch (caught) {
      handleFailure(caught, "Could not load workspace.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void loadWorkspace(), 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const stats = useMemo(() => {
    const active = runs.filter((run) =>
      ["running", "pending"].includes(run.status),
    ).length;
    const completed = runs.filter((run) => run.status === "completed").length;
    const failed = runs.filter((run) => run.status === "failed").length;
    return {
      active,
      completed,
      failed,
      completionRate: runs.length
        ? Math.round((completed / runs.length) * 100)
        : 0,
    };
  }, [runs]);

  const projectRuns = useMemo(
    () =>
      selectedProject
        ? runs.filter((run) => run.project_id === selectedProject.id)
        : [],
    [runs, selectedProject],
  );

  async function openProject(project: Project, resetSection = true) {
    setSelectedProject(project);
    if (resetSection) setProjectSection("datasets");
    setSelectedDataset(null);
    setItems([]);
    setLoadingProject(true);
    setError("");
    try {
      const [datasetList, variantList] = await Promise.all([
        apiRequest<Dataset[]>(`/api/v1/projects/${project.id}/datasets`, {}, token),
        apiRequest<ModelVariant[]>(`/api/v1/projects/${project.id}/variants`, {}, token),
      ]);
      setDatasets(datasetList);
      setVariants(variantList);
    } catch (caught) {
      handleFailure(caught, "Could not load project datasets.");
    } finally {
      setLoadingProject(false);
    }
  }

  function showOverview() {
    setSelectedProject(null);
    setSelectedDataset(null);
    setDatasets([]);
    setVariants([]);
    setItems([]);
    setError("");
  }

  async function selectDataset(dataset: Dataset) {
    setSelectedDataset(dataset);
    setLoadingItems(true);
    setError("");
    try {
      const itemList = await apiRequest<DatasetItem[]>(
        `/api/v1/datasets/${dataset.id}/items`,
        {},
        token,
      );
      setItems(itemList);
    } catch (caught) {
      handleFailure(caught, "Could not load dataset items.");
    } finally {
      setLoadingItems(false);
    }
  }

  async function createProject(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const project = await apiRequest<Project>(
        "/api/v1/projects",
        {
          method: "POST",
          body: JSON.stringify({
            name: projectName.trim(),
            description: projectDescription.trim() || null,
          }),
        },
        token,
      );
      setProjects((current) => [...current, project]);
      setProjectName("");
      setProjectDescription("");
      setShowProjectModal(false);
      await openProject(project);
    } catch (caught) {
      handleFailure(caught, "Could not create project.");
    } finally {
      setSaving(false);
    }
  }

  function openCreateDataset() {
    setDatasetDraft(emptyDatasetDraft);
    setDatasetModal("create");
  }

  function openImportDataset() {
    setImportFile(null);
    setImportName("");
    setImportDescription("");
    setShowImportModal(true);
  }

  function chooseImportFile(file: File | null) {
    setImportFile(file);
    setImportName("");
  }

  async function importDataset(event: FormEvent) {
    event.preventDefault();
    if (!selectedProject || !importFile) return;
    if (importFile.size > 5 * 1024 * 1024) {
      setError("The dataset file must not exceed 5 MB.");
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    const body = new FormData();
    body.append("file", importFile);
    if (importName.trim()) body.append("name", importName.trim());
    if (importDescription.trim()) {
      body.append("description", importDescription.trim());
    }
    try {
      const imported = await apiRequest<DatasetImportResponse>(
        `/api/v1/projects/${selectedProject.id}/datasets/import`,
        { method: "POST", body },
        token,
      );
      setDatasets((current) => [...current, imported.dataset]);
      setShowImportModal(false);
      setNotice(
        `Imported ${imported.item_count} test ${imported.item_count === 1 ? "case" : "cases"} into “${imported.dataset.name}”.`,
      );
      await selectDataset(imported.dataset);
    } catch (caught) {
      handleFailure(caught, "Could not import dataset file.");
    } finally {
      setSaving(false);
    }
  }

  function openEditDataset() {
    if (!selectedDataset) return;
    setDatasetDraft({
      name: selectedDataset.name,
      description: selectedDataset.description ?? "",
    });
    setDatasetModal("edit");
  }

  async function saveDataset(event: FormEvent) {
    event.preventDefault();
    if (!selectedProject) return;
    setSaving(true);
    setError("");
    try {
      const payload = {
        name: datasetDraft.name.trim(),
        description: datasetDraft.description.trim() || null,
      };
      if (datasetModal === "edit" && selectedDataset) {
        const updated = await apiRequest<Dataset>(
          `/api/v1/datasets/${selectedDataset.id}`,
          { method: "PATCH", body: JSON.stringify(payload) },
          token,
        );
        setDatasets((current) =>
          current.map((dataset) =>
            dataset.id === updated.id ? updated : dataset,
          ),
        );
        setSelectedDataset(updated);
      } else {
        const created = await apiRequest<Dataset>(
          `/api/v1/projects/${selectedProject.id}/datasets`,
          { method: "POST", body: JSON.stringify(payload) },
          token,
        );
        setDatasets((current) => [...current, created]);
        await selectDataset(created);
      }
      setDatasetModal(null);
    } catch (caught) {
      handleFailure(caught, "Could not save dataset.");
    } finally {
      setSaving(false);
    }
  }

  async function deleteDataset() {
    if (!selectedDataset) return;
    if (
      !window.confirm(
        `Delete “${selectedDataset.name}” and all of its items? This cannot be undone.`,
      )
    ) {
      return;
    }
    setSaving(true);
    setError("");
    try {
      await apiRequest<void>(
        `/api/v1/datasets/${selectedDataset.id}`,
        { method: "DELETE" },
        token,
      );
      setDatasets((current) =>
        current.filter((dataset) => dataset.id !== selectedDataset.id),
      );
      setSelectedDataset(null);
      setItems([]);
    } catch (caught) {
      handleFailure(caught, "Could not delete dataset.");
    } finally {
      setSaving(false);
    }
  }

  function openCreateItem() {
    setEditingItem(null);
    setItemDraft(emptyItemDraft);
    setItemModal("create");
  }

  function openEditItem(item: DatasetItem) {
    setEditingItem(item);
    setItemDraft({
      externalId: item.external_id,
      input: item.input,
      expectedOutput: item.expected_output,
      keywords: item.keywords.join(", "),
    });
    setItemModal("edit");
  }

  async function saveItem(event: FormEvent) {
    event.preventDefault();
    if (!selectedDataset) return;
    setSaving(true);
    setError("");
    const payload = {
      external_id: itemDraft.externalId.trim(),
      input: itemDraft.input.trim(),
      expected_output: itemDraft.expectedOutput.trim(),
      keywords: itemDraft.keywords
        .split(",")
        .map((keyword) => keyword.trim())
        .filter(Boolean),
    };
    try {
      if (itemModal === "edit" && editingItem) {
        const updated = await apiRequest<DatasetItem>(
          `/api/v1/dataset-items/${editingItem.id}`,
          { method: "PATCH", body: JSON.stringify(payload) },
          token,
        );
        setItems((current) =>
          current.map((item) => (item.id === updated.id ? updated : item)),
        );
      } else {
        const created = await apiRequest<DatasetItem>(
          `/api/v1/datasets/${selectedDataset.id}/items`,
          { method: "POST", body: JSON.stringify(payload) },
          token,
        );
        setItems((current) => [...current, created]);
      }
      setItemModal(null);
      setEditingItem(null);
    } catch (caught) {
      handleFailure(caught, "Could not save dataset item.");
    } finally {
      setSaving(false);
    }
  }

  async function deleteItem(item: DatasetItem) {
    if (!window.confirm(`Delete item “${item.external_id}”?`)) return;
    setSaving(true);
    setError("");
    try {
      await apiRequest<void>(
        `/api/v1/dataset-items/${item.id}`,
        { method: "DELETE" },
        token,
      );
      setItems((current) => current.filter((entry) => entry.id !== item.id));
    } catch (caught) {
      handleFailure(caught, "Could not delete dataset item.");
    } finally {
      setSaving(false);
    }
  }

  const nav = ["Overview", "Projects", "Datasets", "Models", "Evaluation runs"];
  const navIcons = ["◫", "◇", "▤", "M", "↗"];

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">E</span>
          <span>Evalflow</span>
        </div>
        <nav aria-label="Main navigation">
          {nav.map((item, index) => {
            const isAvailable = index < 2 || !!selectedProject;
            const isActive =
              index === 0
                ? !selectedProject
                : index === 1
                  ? false
                : index === 2
                  ? projectSection === "datasets"
                  : index === 3
                    ? projectSection === "models"
                    : projectSection === "runs";
            return (
              <button
                className={`nav-item${isActive ? " active" : ""}`}
                disabled={!isAvailable}
                key={item}
                onClick={
                  index === 0 || index === 1
                    ? showOverview
                    : selectedProject
                      ? () => setProjectSection(index === 2 ? "datasets" : index === 3 ? "models" : "runs")
                      : undefined
                }
                type="button"
              >
                <span className="nav-icon">{navIcons[index]}</span>
                {item}
                {!isAvailable && <small>select project</small>}
              </button>
            );
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className="api-status"><i /> API connected</div>
          <button className="profile" onClick={onLogout} type="button">
            <span>{user?.email.slice(0, 1).toUpperCase() ?? "U"}</span>
            <div>
              <strong>{user?.email.split("@")[0] ?? "Account"}</strong>
              <small>Sign out</small>
            </div>
          </button>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <span className="breadcrumb">
              {selectedProject
                ? `Workspace / Projects / ${selectedProject.name} / ${projectSection}`
                : "Workspace / Overview"}
            </span>
            <h1>{selectedProject?.name ?? "Evaluation overview"}</h1>
            {selectedProject?.description && (
              <p className="topbar-description">{selectedProject.description}</p>
            )}
          </div>
          <div className="top-actions">
            {selectedProject && (
              <button className="secondary-button" onClick={showOverview} type="button">
                ← Overview
              </button>
            )}
            <button
              className="icon-button"
              aria-label="Refresh current view"
              onClick={() =>
                selectedProject
                  ? void openProject(selectedProject, false)
                  : void loadWorkspace()
              }
              type="button"
            >
              ↻
            </button>
            {selectedProject && projectSection === "datasets" && (
              <button className="secondary-button" onClick={openImportDataset} type="button">
                ⇧ Import file
              </button>
            )}
            {(!selectedProject || projectSection === "datasets") && <button
              className="primary-button"
              onClick={
                selectedProject
                  ? openCreateDataset
                  : () => setShowProjectModal(true)
              }
              type="button"
            >
              <span>＋</span> {selectedProject ? "New dataset" : "New project"}
            </button>}
          </div>
        </header>

        {error && (
          <div className="error-banner" role="alert">
            {error}
            <button onClick={() => setError("")} type="button">×</button>
          </div>
        )}
        {notice && (
          <div className="success-banner" role="status">
            <span>✓</span> {notice}
            <button onClick={() => setNotice("")} type="button">×</button>
          </div>
        )}

        {loading ? (
          <LoadingState label="Loading your evaluation workspace…" />
        ) : selectedProject && projectSection === "datasets" ? (
          <ProjectWorkspace
            datasets={datasets}
            items={items}
            loadingProject={loadingProject}
            loadingItems={loadingItems}
            onCreateDataset={openCreateDataset}
            onImportDataset={openImportDataset}
            onCreateItem={openCreateItem}
            onDeleteDataset={() => void deleteDataset()}
            onDeleteItem={(item) => void deleteItem(item)}
            onEditDataset={openEditDataset}
            onEditItem={openEditItem}
            onSelectDataset={(dataset) => void selectDataset(dataset)}
            projectRuns={projectRuns}
            selectedDataset={selectedDataset}
          />
        ) : selectedProject && projectSection === "models" ? (
          <ModelWorkspace
            token={token}
            project={selectedProject}
            variants={variants}
            onVariantsChange={setVariants}
            onFailure={handleFailure}
            onNotice={setNotice}
          />
        ) : selectedProject ? (
          <RunWorkspace
            token={token}
            project={selectedProject}
            datasets={datasets}
            variants={variants}
            runs={projectRuns}
            onRunChange={upsertRun}
            onFailure={handleFailure}
            onNotice={setNotice}
          />
        ) : (
          <Overview
            projects={projects}
            runs={runs}
            stats={stats}
            onCreateProject={() => setShowProjectModal(true)}
            onOpenProject={(project) => void openProject(project)}
          />
        )}
      </section>

      {showProjectModal && (
        <Modal titleId="new-project-title" onClose={() => setShowProjectModal(false)}>
          <span className="panel-kicker">NEW WORKSPACE PROJECT</span>
          <h2 id="new-project-title">Create a project</h2>
          <p>Projects keep datasets, model variants, and evaluation history together.</p>
          <form onSubmit={createProject}>
            <label>
              Project name
              <input maxLength={200} value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="Customer support benchmark" required />
            </label>
            <label>
              Description
              <textarea value={projectDescription} onChange={(event) => setProjectDescription(event.target.value)} placeholder="What are you evaluating?" rows={3} />
            </label>
            <ModalActions saving={saving} onCancel={() => setShowProjectModal(false)} label="Create project" />
          </form>
        </Modal>
      )}

      {datasetModal && (
        <Modal titleId="dataset-title" onClose={() => setDatasetModal(null)}>
          <span className="panel-kicker">DATASET</span>
          <h2 id="dataset-title">{datasetModal === "edit" ? "Edit dataset" : "Create a dataset"}</h2>
          <p>A dataset groups prompts, reference answers, and evaluation keywords.</p>
          <form onSubmit={saveDataset}>
            <label>
              Dataset name
              <input maxLength={200} value={datasetDraft.name} onChange={(event) => setDatasetDraft((current) => ({ ...current, name: event.target.value }))} placeholder="Reasoning benchmark" required />
            </label>
            <label>
              Description
              <textarea value={datasetDraft.description} onChange={(event) => setDatasetDraft((current) => ({ ...current, description: event.target.value }))} placeholder="What does this dataset measure?" rows={3} />
            </label>
            <ModalActions saving={saving} onCancel={() => setDatasetModal(null)} label={datasetModal === "edit" ? "Save changes" : "Create dataset"} />
          </form>
        </Modal>
      )}

      {showImportModal && (
        <Modal titleId="import-title" onClose={() => setShowImportModal(false)} wide>
          <span className="panel-kicker">BULK IMPORT</span>
          <h2 id="import-title">Import dataset from file</h2>
          <p>Upload JSONL, NDJSON, or JSON. Evalflow validates every test case before saving anything.</p>
          <form onSubmit={importDataset}>
            <label className={`file-drop${importFile ? " has-file" : ""}`}>
              <input accept=".json,.jsonl,.ndjson,application/json,application/x-ndjson" onChange={(event) => chooseImportFile(event.target.files?.[0] ?? null)} type="file" required />
              <span className="file-drop-icon">⇧</span>
              <strong>{importFile?.name ?? "Choose a dataset file"}</strong>
              <small>{importFile ? `${(importFile.size / 1024).toFixed(1)} KB selected` : "JSONL, NDJSON, or JSON · maximum 5 MB"}</small>
            </label>
            <div className="form-grid">
              <label>
                Dataset name <small>derived from filename</small>
                <input maxLength={200} value={importName} onChange={(event) => setImportName(event.target.value)} placeholder={importFile ? importFile.name.replace(/\.(jsonl|ndjson|json)$/i, "") : "questions"} />
              </label>
              <label>
                Description <small>optional</small>
                <input value={importDescription} onChange={(event) => setImportDescription(event.target.value)} placeholder="Imported benchmark" />
              </label>
            </div>
            <div className="format-help">
              <div className="format-help-head"><strong>Expected test-case fields</strong><a href="/examples/dataset-template.json" download>Download template ↓</a></div>
              <code>{`{"id":"1","input":"Question","expected_output":"Answer","keywords":["Answer"]}`}</code>
              <small>`external_id` can be used instead of `id`. JSON files may contain an array or an object with `name`, `description`, and `items`.</small>
            </div>
            <ModalActions saving={saving} onCancel={() => setShowImportModal(false)} label="Import dataset" />
          </form>
        </Modal>
      )}

      {itemModal && (
        <Modal titleId="item-title" onClose={() => setItemModal(null)} wide>
          <span className="panel-kicker">TEST CASE</span>
          <h2 id="item-title">{itemModal === "edit" ? "Edit test case" : "Add a test case"}</h2>
          <p>Every test case becomes one request for each selected model variant.</p>
          <form onSubmit={saveItem}>
            <div className="form-grid">
              <label>
                External ID
                <input maxLength={200} value={itemDraft.externalId} onChange={(event) => setItemDraft((current) => ({ ...current, externalId: event.target.value }))} placeholder="question-001" required />
              </label>
              <label>
                Keywords <small>comma-separated</small>
                <input value={itemDraft.keywords} onChange={(event) => setItemDraft((current) => ({ ...current, keywords: event.target.value }))} placeholder="Paris, France" />
              </label>
            </div>
            <label>
              Input prompt
              <textarea value={itemDraft.input} onChange={(event) => setItemDraft((current) => ({ ...current, input: event.target.value }))} placeholder="What is the capital of France?" rows={4} required />
            </label>
            <label>
              Expected output
              <textarea value={itemDraft.expectedOutput} onChange={(event) => setItemDraft((current) => ({ ...current, expectedOutput: event.target.value }))} placeholder="Paris" rows={3} />
            </label>
            <ModalActions saving={saving} onCancel={() => setItemModal(null)} label={itemModal === "edit" ? "Save changes" : "Add test case"} />
          </form>
        </Modal>
      )}
    </main>
  );
}

function LoadingState({ label }: { label: string }) {
  return <div className="dashboard-loading"><span /><p>{label}</p></div>;
}

function Modal({ children, onClose, titleId, wide = false }: { children: React.ReactNode; onClose: () => void; titleId: string; wide?: boolean }) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className={`modal${wide ? " modal-wide" : ""}`} role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <button className="modal-close" onClick={onClose} aria-label="Close dialog" type="button">×</button>
        {children}
      </section>
    </div>
  );
}

function ModalActions({ saving, onCancel, label }: { saving: boolean; onCancel: () => void; label: string }) {
  return (
    <div className="modal-actions">
      <button className="secondary-button" onClick={onCancel} type="button">Cancel</button>
      <button className="primary-button" disabled={saving} type="submit">{saving ? "Saving…" : label}</button>
    </div>
  );
}

function Overview({ projects, runs, stats, onCreateProject, onOpenProject }: { projects: Project[]; runs: EvaluationRun[]; stats: { active: number; completed: number; failed: number; completionRate: number }; onCreateProject: () => void; onOpenProject: (project: Project) => void }) {
  return (
    <>
      <section className="metric-grid" aria-label="Workspace metrics">
        <Metric label="TOTAL PROJECTS" value={projects.length} note={projects.length ? "Ready for evaluation" : "Create your first project"} icon="◇" tone="purple" />
        <Metric label="EVALUATION RUNS" value={runs.length} note={stats.active ? `${stats.active} currently active` : "No active runs"} icon="↗" tone="blue" />
        <Metric label="COMPLETION RATE" value={`${stats.completionRate}%`} note={`${stats.completed} successful runs`} icon="✓" tone="green" />
        <Metric label="FAILED RUNS" value={stats.failed} note={stats.failed ? "Review provider errors" : "Everything looks healthy"} icon="!" tone="orange" />
      </section>
      <section className="dashboard-grid">
        <article className="panel performance-panel">
          <div className="panel-head"><div><span className="panel-kicker">RUN HEALTH</span><h2>Evaluation activity</h2></div><span className="period-pill">All time</span></div>
          {runs.length ? (
            <><div className="activity-chart"><div className="grid-lines" />{runs.slice(0, 12).reverse().map((run, index) => { const progress = run.total_tasks ? run.completed_tasks / run.total_tasks : 0.08; return <div className={`activity-bar bar-${run.status}`} key={run.id} style={{ height: `${Math.max(8, progress * 100)}%` }}><span>{index + 1}</span></div>; })}</div><div className="activity-legend"><span><i className="legend-completed" /> Completed</span><span><i className="legend-running" /> Active</span><span><i className="legend-failed" /> Failed / cancelled</span></div></>
          ) : (
            <div className="empty-chart"><div className="empty-bars"><i /><i /><i /><i /><i /><i /></div><strong>Your activity chart starts here</strong><p>Launch an evaluation to see progress and outcomes over time.</p></div>
          )}
        </article>
        <article className="panel projects-panel">
          <div className="panel-head"><div><span className="panel-kicker">WORKSPACE</span><h2>Projects</h2></div><button className="text-button" onClick={onCreateProject} type="button">Add project →</button></div>
          <div className="project-list">
            {projects.length ? projects.slice(0, 5).map((project, index) => (
              <button className="project-row" key={project.id} onClick={() => onOpenProject(project)} type="button"><span className={`project-avatar tone-${index % 4}`}>{project.name.slice(0, 2).toUpperCase()}</span><span className="project-row-copy"><strong>{project.name}</strong><small>{project.description || "No description"}</small></span><span className="project-date">{formatDate(project.updated_at)}<i>→</i></span></button>
            )) : <div className="mini-empty"><span>◇</span><strong>No projects yet</strong><p>Create a project to group datasets, models, and runs.</p></div>}
          </div>
        </article>
      </section>
      <RunsTable projects={projects} runs={runs.slice(0, 6)} />
    </>
  );
}

function Metric({ label, value, note, icon, tone }: { label: string; value: string | number; note: string; icon: string; tone: string }) {
  return <article className="metric-card"><span className="metric-label">{label}</span><strong>{value}</strong><small>{note}</small><i className={`metric-orb ${tone}`}>{icon}</i></article>;
}

function ProjectWorkspace({ datasets, items, selectedDataset, projectRuns, loadingProject, loadingItems, onCreateDataset, onImportDataset, onSelectDataset, onEditDataset, onDeleteDataset, onCreateItem, onEditItem, onDeleteItem }: { datasets: Dataset[]; items: DatasetItem[]; selectedDataset: Dataset | null; projectRuns: EvaluationRun[]; loadingProject: boolean; loadingItems: boolean; onCreateDataset: () => void; onImportDataset: () => void; onSelectDataset: (dataset: Dataset) => void; onEditDataset: () => void; onDeleteDataset: () => void; onCreateItem: () => void; onEditItem: (item: DatasetItem) => void; onDeleteItem: (item: DatasetItem) => void }) {
  if (loadingProject) return <LoadingState label="Loading project datasets…" />;
  return (
    <>
      <section className="project-metrics">
        <Metric label="DATASETS" value={datasets.length} note="Benchmark collections" icon="▤" tone="purple" />
        <Metric label="SELECTED ITEMS" value={selectedDataset ? items.length : "—"} note={selectedDataset ? selectedDataset.name : "Choose a dataset"} icon="≡" tone="blue" />
        <Metric label="PROJECT RUNS" value={projectRuns.length} note="Saved evaluations" icon="↗" tone="green" />
      </section>
      <section className="dataset-workspace">
        <aside className="panel dataset-list-panel">
          <div className="panel-head"><div><span className="panel-kicker">COLLECTIONS</span><h2>Datasets</h2></div><button className="square-button" onClick={onCreateDataset} aria-label="Create dataset" type="button">＋</button></div>
          <div className="dataset-list">
            {datasets.length ? datasets.map((dataset) => (
              <button className={`dataset-card${selectedDataset?.id === dataset.id ? " active" : ""}`} key={dataset.id} onClick={() => onSelectDataset(dataset)} type="button"><span className="dataset-icon">▤</span><span><strong>{dataset.name}</strong><small>{dataset.description || "No description"}</small></span><i>→</i></button>
            )) : <div className="dataset-empty"><span>▤</span><strong>No datasets yet</strong><p>Create one manually or import a ready benchmark file.</p><div className="empty-actions"><button className="primary-button" onClick={onImportDataset} type="button">⇧ Import file</button><button className="secondary-button" onClick={onCreateDataset} type="button">Create manually</button></div></div>}
          </div>
        </aside>

        <article className="panel dataset-detail-panel">
          {selectedDataset ? (
            <>
              <div className="dataset-detail-head"><div><span className="panel-kicker">SELECTED DATASET</span><h2>{selectedDataset.name}</h2><p>{selectedDataset.description || "No description provided."}</p></div><div className="dataset-actions"><button className="secondary-button" onClick={onEditDataset} type="button">Edit</button><button className="danger-button" onClick={onDeleteDataset} type="button">Delete</button><button className="primary-button" onClick={onCreateItem} type="button">＋ Add test case</button></div></div>
              {loadingItems ? <LoadingState label="Loading test cases…" /> : (
                <div className="item-table-wrap">
                  <table className="item-table">
                    <thead><tr><th>ID</th><th>Input</th><th>Expected output</th><th>Keywords</th><th aria-label="Actions" /></tr></thead>
                    <tbody>{items.length ? items.map((item) => (
                      <tr key={item.id}><td><strong>{item.external_id}</strong><small>{shortId(item.id)}</small></td><td><span className="clamped-cell">{item.input}</span></td><td><span className="clamped-cell">{item.expected_output || "—"}</span></td><td><div className="keyword-list">{item.keywords.length ? item.keywords.slice(0, 3).map((keyword) => <span key={keyword}>{keyword}</span>) : <small>None</small>}</div></td><td><div className="row-actions"><button onClick={() => onEditItem(item)} type="button">Edit</button><button className="danger-text" onClick={() => onDeleteItem(item)} type="button">Delete</button></div></td></tr>
                    )) : <tr><td className="table-empty" colSpan={5}>This dataset has no test cases yet. Add a prompt and expected answer to begin.</td></tr>}</tbody>
                  </table>
                </div>
              )}
            </>
          ) : (
            <div className="detail-empty"><span>←</span><strong>Select a dataset</strong><p>Choose a collection to inspect, edit, and add test cases.</p></div>
          )}
        </article>
      </section>
      {projectRuns.length > 0 && <RunsTable projects={[]} runs={projectRuns.slice(0, 6)} />}
    </>
  );
}

function RunsTable({ projects, runs }: { projects: Project[]; runs: EvaluationRun[] }) {
  return (
    <section className="panel runs-panel"><div className="panel-head"><div><span className="panel-kicker">LATEST ACTIVITY</span><h2>Recent evaluation runs</h2></div><span className="period-pill">{runs.length} shown</span></div><div className="table-wrap"><table><thead><tr><th>Run</th><th>Project</th><th>Status</th><th>Progress</th><th>Concurrency</th><th>Created</th></tr></thead><tbody>{runs.length ? runs.map((run) => { const project = projects.find((item) => item.id === run.project_id); const progress = run.total_tasks ? Math.round((run.completed_tasks / run.total_tasks) * 100) : 0; return <tr key={run.id}><td><strong>run_{shortId(run.id)}</strong><small>{shortId(run.dataset_id)}</small></td><td>{project?.name ?? `Project ${shortId(run.project_id)}`}</td><td><StatusBadge status={run.status} /></td><td><div className="progress-cell"><span><i style={{ width: `${progress}%` }} /></span><small>{progress}%</small></div></td><td>{run.concurrency} workers</td><td>{formatDate(run.created_at)}</td></tr>; }) : <tr><td className="table-empty" colSpan={6}>No evaluation runs yet. Open a project, prepare its dataset and models, then launch a comparison.</td></tr>}</tbody></table></div></section>
  );
}
