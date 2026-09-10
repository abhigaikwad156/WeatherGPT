import { NavLink, Outlet } from "react-router-dom";

const navigation = [
  ["/dashboard", "Dashboard", "⌂"],
  ["/farm", "My farm", "⌖"],
  ["/crops", "My crops", "♧"],
  ["/weather", "Weather", "☀"],
  ["/recommendations", "Recommendations", "✓"],
  ["/alerts", "Alerts", "!"],
  ["/chat", "Ask WeatherGPT", "◌"],
  ["/settings", "Settings", "⚙"]
];

export function AppShell() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <NavLink to="/dashboard" className="brand"><span className="brand-mark">☼</span><span><strong>Weather</strong><small>GPT</small></span></NavLink>
        <div className="sidebar-profile"><span className="avatar">RK</span><div><strong>Ramesh Kumar</strong><small>Green Valley Farm</small></div></div>
        <p className="sidebar-label">Your farm</p>
        <nav aria-label="Primary navigation">
          {navigation.map(([to, label, icon]) => (
            <NavLink key={to} to={to} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
              <span aria-hidden="true">{icon}</span>{label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-help"><span className="help-icon">?</span><div><strong>Need help?</strong><p>Ask WeatherGPT in Marathi, Hindi, or English.</p></div></div>
      </aside>
      <main className="main-content"><header className="topbar"><div className="location"><span>⌖</span><div><small>FARM LOCATION</small><strong>Green Valley Farm, Pune</strong></div></div><div className="topbar-actions"><button className="icon-button" aria-label="Notifications">♢<span className="notification-dot" /></button><NavLink to="/settings" className="topbar-user"><span className="avatar avatar-small">RK</span><span>Ramesh</span><b>⌄</b></NavLink></div></header><Outlet /></main>
      <nav className="mobile-nav" aria-label="Mobile navigation">
        {navigation.slice(0, 5).map(([to, label, icon]) => <NavLink key={to} to={to}><span>{icon}</span><small>{label}</small></NavLink>)}
      </nav>
    </div>
  );
}
