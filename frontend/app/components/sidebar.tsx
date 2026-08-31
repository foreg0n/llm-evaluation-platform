export type SidebarItem = {
  label: string;
  icon: string;
  available: boolean;
  active: boolean;
  action: () => void;
};

export function Sidebar({
  collapsed,
  items,
  onLogout,
  onToggle,
  userEmail,
}: {
  collapsed: boolean;
  items: SidebarItem[];
  onLogout: () => void;
  onToggle: () => void;
  userEmail?: string;
}) {
  const workspaceItems = items.filter((item) => item.label !== "Settings");
  const settingsItems = items.filter((item) => item.label === "Settings");

  function renderItem(item: SidebarItem) {
    return (
      <button
        className={`nav-item${item.active ? " active" : ""}`}
        disabled={!item.available}
        key={item.label}
        onClick={item.available ? item.action : undefined}
        title={collapsed ? item.label : undefined}
        type="button"
      >
        <span className="nav-icon">{item.icon}</span>
        <span className="nav-label">{item.label}</span>
        {!item.available && <small>select project</small>}
      </button>
    );
  }

  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark">E</span>
        <span className="brand-label">Evalflow</span>
        <button
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="sidebar-toggle"
          onClick={onToggle}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          type="button"
        >
          {collapsed ? "›" : "‹"}
        </button>
      </div>
      <nav aria-label="Main navigation">
        <span className="nav-section-label">Workspace</span>
        {workspaceItems.map(renderItem)}
        <span className="nav-section-label nav-section-secondary">Configuration</span>
        {settingsItems.map(renderItem)}
      </nav>
      <div className="sidebar-bottom">
        <div className="api-status">
          <i /> API connected
        </div>
        <button className="profile" onClick={onLogout} type="button">
          <span>{userEmail?.slice(0, 1).toUpperCase() ?? "U"}</span>
          <div>
            <strong>{userEmail?.split("@")[0] ?? "Account"}</strong>
            <small>Sign out</small>
          </div>
        </button>
      </div>
    </aside>
  );
}
