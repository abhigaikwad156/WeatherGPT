import { useEffect } from "react";
import { Navigate, Outlet, Route, Routes, useNavigate } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { AuthPage, AlertsPage, CropsPage, RecommendationsPage, ResourcePage, WeatherPage } from "./pages/FeaturePages";
import { ChatPage } from "./pages/ChatPage";
import { DashboardPage } from "./pages/DashboardPage";
import { FarmPage } from "./pages/FarmPage";
import { LocationProvider } from "./location/LocationContext";

function RequireAuthentication() {
  return localStorage.getItem("weathergpt_access_token") ? <Outlet /> : <Navigate to="/login" replace />;
}

export function App() {
  const navigate = useNavigate();

  useEffect(() => {
    const returnToLogin = () => navigate("/login", { replace: true });
    window.addEventListener("weathergpt:unauthorized", returnToLogin);
    return () => window.removeEventListener("weathergpt:unauthorized", returnToLogin);
  }, [navigate]);

  return (
    <Routes>
      <Route path="/login" element={<AuthPage mode="login" />} />
      <Route path="/register" element={<AuthPage mode="register" />} />
      <Route element={<RequireAuthentication />}>
        <Route element={<LocationProvider><AppShell /></LocationProvider>}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/farm" element={<FarmPage />} />
          <Route path="/crops" element={<CropsPage />} />
          <Route path="/weather" element={<WeatherPage />} />
          <Route path="/recommendations" element={<RecommendationsPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/settings" element={<ResourcePage resource="profile" />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
