import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import type { Crop, FarmWeather } from "../api/types";
import { weatherGptApi } from "../api/weatherGpt";
import { AlertCard, ForecastCard, RecommendationCard, WeatherCard } from "../components/dataCards";
import { Card, EmptyState, ErrorState, LoadingState } from "../components/ui";
import { useResource } from "../hooks/useResource";

const featureConfig = {
  profile: { title: "Profile & settings", description: "Language and account preferences.", load: weatherGptApi.getProfile }
};

export function ResourcePage({ resource }: { resource: keyof typeof featureConfig }) {
  const config = featureConfig[resource];
  const state = useResource(config.load);
  return <div className="page"><header className="page-header"><div><p className="eyebrow">WeatherGPT</p><h1>{config.title}</h1><p>{config.description}</p></div></header><Card>{state.loading && <LoadingState />}{state.error && <ErrorState message={state.error} retry={state.refresh} />}{!state.loading && !state.error && <EmptyState title={`No ${config.title.toLowerCase()} data yet`} description="This information will appear here when the matching backend API is available." />}</Card></div>;
}

export function CropsPage() {
  const [farmId, setFarmId] = useState<string>();
  const [crops, setCrops] = useState<Crop[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

  const loadCrops = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const farms = await weatherGptApi.getFarms();
      if (!farms.length) throw new Error("Add a farm before adding crops.");
      setFarmId(farms[0].id);
      setCrops(await weatherGptApi.getFarmCrops(farms[0].id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load crops.");
    } finally {
      setLoading(false);
    }
  }, []);

  const createCrop = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!farmId) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setSaving(true);
    setError(null);
    try {
      const crop = await weatherGptApi.createCrop(farmId, {
        name: String(form.get("name")).trim(),
        variety: String(form.get("variety")).trim() || undefined,
        sowing_date: String(form.get("sowingDate")).trim() || undefined,
        growth_stage: String(form.get("growthStage")).trim() || undefined
      });
      setCrops((current) => [crop, ...current]);
      formRef.current?.reset();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to save crop.");
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    void loadCrops();
  }, [loadCrops]);

  return <div className="page"><header className="page-header"><div><p className="eyebrow">WeatherGPT</p><h1>My crops</h1><p>Track crops for your farm and unlock crop-specific advice.</p></div></header>{loading && <LoadingState label="Loading crops…" />}{error && <ErrorState message={error} retry={loadCrops} />}{!loading && !error && <>{crops.length ? <div className="stack">{crops.map((crop) => <Card key={crop.id}><p className="eyebrow">{crop.is_active ? "Active crop" : "Inactive crop"}</p><h2>{crop.name}</h2><p>{crop.variety || "Variety not set"} · {crop.growth_stage || "Growth stage not set"}</p>{crop.sowing_date && <small>Sown {crop.sowing_date}</small>}</Card>)}</div> : <Card><EmptyState title="No crops added yet" description="Add your first crop below." /></Card>}<Card><div className="card-heading"><div><p className="eyebrow">Crop details</p><h2>Add a crop</h2></div></div><form ref={formRef} className="farm-form" onSubmit={createCrop}><label>Crop name<input name="name" required minLength={2} placeholder="Onion" /></label><label>Variety<input name="variety" placeholder="Optional variety" /></label><div className="form-row"><label>Sowing date<input name="sowingDate" type="date" /></label><label>Growth stage<input name="growthStage" placeholder="Vegetative" /></label></div><button className="primary-button" disabled={saving}>{saving ? "Saving crop…" : "Save crop"}</button></form></Card></>}</div>;
}

export function WeatherPage() {
  const loadWeather = useCallback(async (): Promise<FarmWeather> => {
    const farms = await weatherGptApi.getFarms();
    if (!farms.length) throw new Error("Add a farm before viewing weather.");
    return weatherGptApi.getFarmWeather(farms[0].id);
  }, []);
  const state = useResource(loadWeather);
  const current = state.data?.current;
  const weather = current
    ? {
        temperatureCelsius: current.temperature_celsius ?? 0,
        condition: current.condition ?? "Unknown",
        rainfallMm: current.rainfall_mm ?? 0,
        observedAt: current.observed_at
      }
    : null;
  return <div className="page"><header className="page-header"><div><p className="eyebrow">Open-Meteo</p><h1>Weather</h1><p>Current conditions and forecast for your first saved farm.</p></div></header>{state.loading && <LoadingState label="Loading live weather…" />}{state.error && <ErrorState message={state.error} retry={state.refresh} />}{weather && state.data && <div className="content-grid"><WeatherCard weather={weather} /><ForecastCard items={state.data.daily.map((item) => ({ forecastFor: item.forecast_for, temperatureMinCelsius: item.temperature_min_celsius, temperatureMaxCelsius: item.temperature_max_celsius, precipitationMm: item.precipitation_mm, rainProbabilityPercent: item.rain_probability_percent }))} /></div>}</div>;
}

export function RecommendationsPage() {
  const state = useResource(weatherGptApi.getRecommendations);
  return <div className="page"><header className="page-header"><div><p className="eyebrow">Decision support</p><h1>Agricultural recommendations</h1><p>Recommendations are generated by the backend decision engine with supporting evidence.</p></div></header><Card>{state.loading && <LoadingState />}{state.error && <ErrorState message={state.error} retry={state.refresh} />}{!state.loading && !state.error && Array.isArray(state.data) && state.data.length > 0 ? <div className="stack">{state.data.map((item) => <RecommendationCard key={item.id} recommendation={item} />)}</div> : !state.loading && !state.error && <EmptyState title="No recommendations yet" description="Recommendations will be shown here once farm, crop, and weather data are available." />}</Card></div>;
}

export function AlertsPage() {
  const state = useResource(weatherGptApi.getAlerts);
  return <div className="page"><header className="page-header"><div><p className="eyebrow">Safety first</p><h1>Weather alerts</h1><p>Important weather risks for your farm will appear here.</p></div></header><Card>{state.loading && <LoadingState />}{state.error && <ErrorState message={state.error} retry={state.refresh} />}{!state.loading && !state.error && Array.isArray(state.data) && state.data.length > 0 ? <div className="stack">{state.data.map((item) => <AlertCard key={item.id} alert={item} />)}</div> : !state.loading && !state.error && <EmptyState title="No active alerts" description="You will see weather alerts here when alert rules are configured." />}</Card></div>;
}

export function AuthPage({ mode }: { mode: "login" | "register" }) {
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const isRegister = mode === "register";
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setSubmitting(true); setError(null);
    const form = new FormData(event.currentTarget);
    try {
      const response = isRegister
        ? await weatherGptApi.register({ display_name: String(form.get("name")), email: String(form.get("email")), password: String(form.get("password")) })
        : await weatherGptApi.login({ email: String(form.get("email")), password: String(form.get("password")) });
      localStorage.setItem("weathergpt_access_token", response.access_token);
      window.location.href = "/dashboard";
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to continue."); } finally { setSubmitting(false); }
  };
  return <main className="auth-page"><section className="auth-intro"><span>🌱</span><h1>WeatherGPT</h1><p>Clear, practical weather support for your farm.</p></section><section className="auth-card"><p className="eyebrow">Welcome</p><h2>{isRegister ? "Create your farmer account" : "Sign in to your account"}</h2><form onSubmit={submit}>{isRegister && <label>Name<input name="name" required autoComplete="name" /></label>}<label>Email<input name="email" required type="email" autoComplete="email" /></label><label>Password<input name="password" required type="password" minLength={8} autoComplete={isRegister ? "new-password" : "current-password"} /></label>{error && <p className="form-error" role="alert">{error}</p>}<button className="primary-button" disabled={submitting}>{submitting ? "Please wait…" : isRegister ? "Create account" : "Sign in"}</button></form><p>{isRegister ? "Already have an account?" : "New to WeatherGPT?"} <a href={isRegister ? "/login" : "/register"}>{isRegister ? "Sign in" : "Create an account"}</a></p></section></main>;
}
