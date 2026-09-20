import { NavLink, Outlet } from "react-router-dom";

import { weatherGptApi } from "../api/weatherGpt";
import { useResource } from "../hooks/useResource";
import { useCurrentLocation } from "../location/LocationContext";
import { locationDisplayName } from "../location/locationDisplay";
import { LocationConsent } from "./LocationConsent";

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
  const { currentLocation, loadingSavedLocation } = useCurrentLocation();
  const profile = useResource(weatherGptApi.getProfile);
  const displayName = profile.data?.display_name ?? "Your account";
  const firstName = profile.data?.display_name.split(" ")[0] ?? "Account";
  const initials = profile.data?.display_name
    .split(" ")
    .map((name) => name[0])
    .join("")
    .slice(0, 2)
    .toUpperCase() ?? "?";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <NavLink to="/dashboard" className="brand"><span className="brand-mark">☼</span><span><strong>Weather</strong><small>GPT</small></span></NavLink>
        <div className="sidebar-profile"><span className="avatar">{initials}</span><div><strong>{displayName}</strong><small>Green Valley Farm</small></div></div>
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
      <main className="main-content">
        <header className="topbar">
          <div className="location"><span>⌖</span><div><small>CURRENT LOCATION</small><strong>{loadingSavedLocation ? "Checking saved location…" : locationDisplayName(currentLocation)}</strong></div></div>
          <div className="topbar-actions"><details className="location-menu"><summary>Update location</summary><LocationConsent /><small className="osm-attribution">© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a></small></details><button className="icon-button" aria-label="Notifications">♢<span className="notification-dot" /></button><NavLink to="/settings" className="topbar-user"><span className="avatar avatar-small">{initials}</span><span>{firstName}</span><b>⌄</b></NavLink></div>
        </header>
        <Outlet />
      </main>
      <nav className="mobile-nav" aria-label="Mobile navigation">
        {navigation.slice(0, 5).map(([to, label, icon]) => <NavLink key={to} to={to}><span>{icon}</span><small>{label}</small></NavLink>)}
      </nav>
    </div>
  );
}
