import { useEffect, useState } from "react";
import { Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import {
  hasActiveAccessToken,
  SESSION_CHANGED_EVENT,
  UNAUTHORIZED_EVENT
} from "./auth/session";
import { AppShell } from "./components/AppShell";
import { AuthPage, AlertsPage, CropsPage, RecommendationsPage, ResourcePage, WeatherPage } from "./pages/FeaturePages";
import { ChatPage } from "./pages/ChatPage";
import { CropHealthPage } from "./pages/CropHealthPage";
import { DashboardPage } from "./pages/DashboardPage";
import { FarmPage } from "./pages/FarmPage";
import { LocationProvider } from "./location/LocationContext";

function RequireAuthentication() {
  const hasAccessToken = hasActiveAccessToken();
  return hasAccessToken ? <Outlet /> : <Navigate to="/login" replace />;
}

export function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const [sessionVersion, setSessionVersion] = useState(0);

  useEffect(() => {
    const returnToLogin = () => {
      if (location.pathname !== "/login" && location.pathname !== "/register") {
        navigate("/login", { replace: true });
      }
    };
    const resetProtectedState = () => {
      setSessionVersion((version) => version + 1);
      returnToLogin();
    };

    window.addEventListener(UNAUTHORIZED_EVENT, returnToLogin);
    window.addEventListener(SESSION_CHANGED_EVENT, resetProtectedState);
    return () => {
      window.removeEventListener(UNAUTHORIZED_EVENT, returnToLogin);
      window.removeEventListener(SESSION_CHANGED_EVENT, resetProtectedState);
    };
  }, [location.pathname, navigate]);

  return (
    <Routes key={sessionVersion}>
      <Route path="/login" element={<AuthPage mode="login" />} />
      <Route path="/register" element={<AuthPage mode="register" />} />
      <Route element={<RequireAuthentication />}>
        <Route element={<LocationProvider><AppShell /></LocationProvider>}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/farm" element={<FarmPage />} />
          <Route path="/crops" element={<CropsPage />} />
          <Route path="/crop-health" element={<CropHealthPage />} />
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
