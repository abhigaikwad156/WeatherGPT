import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { AuthPage, AlertsPage, RecommendationsPage, ResourcePage } from "./pages/FeaturePages";
import { ChatPage } from "./pages/ChatPage";
import { DashboardPage } from "./pages/DashboardPage";
import { FarmPage } from "./pages/FarmPage";

export function App() {
  return <Routes><Route path="/login" element={<AuthPage mode="login" />} /><Route path="/register" element={<AuthPage mode="register" />} /><Route element={<AppShell />}><Route path="/dashboard" element={<DashboardPage />} /><Route path="/farm" element={<FarmPage />} /><Route path="/crops" element={<ResourcePage resource="crops" />} /><Route path="/weather" element={<ResourcePage resource="weather" />} /><Route path="/recommendations" element={<RecommendationsPage />} /><Route path="/alerts" element={<AlertsPage />} /><Route path="/chat" element={<ChatPage />} /><Route path="/settings" element={<ResourcePage resource="profile" />} /></Route><Route path="*" element={<Navigate to="/dashboard" replace />} /></Routes>;
}
