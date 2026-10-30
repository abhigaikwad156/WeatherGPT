import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { Crop, FarmerProfile, FarmWeather } from "../api/types";
import { ApiError } from "../api/client";
import { weatherGptApi } from "../api/weatherGpt";
import { storeAccessToken } from "../auth/session";
import { AlertCard, ForecastCard, WeatherCard } from "../components/dataCards";
import { Card, EmptyState, ErrorState, LoadingState } from "../components/ui";
import { useResource } from "../hooks/useResource";

const featureConfig = {
  profile: { title: "Profile & settings", description: "Language and account preferences.", load: weatherGptApi.getProfile }
};

export function ResourcePage({ resource }: { resource: keyof typeof featureConfig }) {
  const config = featureConfig[resource];
  const [profile, setProfile] = useState<FarmerProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saving, setSaving] = useState(false);
  const [preferredLanguage, setPreferredLanguage] = useState("");
  const [preferredUnits, setPreferredUnits] = useState("");

  const loadProfile = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const savedProfile = await config.load();
      setProfile(savedProfile);
      setPreferredLanguage(savedProfile.preferred_language ?? "");
      setPreferredUnits(savedProfile.preferred_units ?? "");
    } catch (caught) {
      setLoadError(caught instanceof Error ? caught.message : "Unable to load your profile.");
    } finally {
      setLoading(false);
    }
  }, [config]);

  useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!profile || saving) return;
    setSaving(true);
    setSaveError(null);
    setSaveSuccess(false);
    try {
      const changes: {
        preferred_language?: string;
        preferred_units?: "metric" | "imperial";
      } = { preferred_language: preferredLanguage };
      if (
        (preferredUnits === "metric" || preferredUnits === "imperial")
        && preferredUnits !== profile.preferred_units
      ) {
        changes.preferred_units = preferredUnits;
      }
      const updatedProfile = await weatherGptApi.updateProfile(changes);
      setProfile(updatedProfile);
      setPreferredLanguage(updatedProfile.preferred_language ?? "");
      setPreferredUnits(updatedProfile.preferred_units ?? "");
      setSaveSuccess(true);
    } catch (caught) {
      setSaveError(
        caught instanceof ApiError && caught.status === 422
          ? `Please check your selected preferences. ${caught.message}`
          : caught instanceof Error
            ? caught.message
            : "Unable to save your preferences. Please try again."
      );
    } finally {
      setSaving(false);
    }
  }

  return <div className="page"><header className="page-header"><div><p className="eyebrow">WeatherGPT</p><h1>{config.title}</h1><p>{config.description}</p></div></header>{loading && !profile && <LoadingState label="Loading your profile…" />}{loadError && !profile && <ErrorState message={loadError} retry={loadProfile} />}{profile && <><Card><div className="card-heading"><div><p className="eyebrow">Account</p><h2>{profile.display_name}</h2></div></div><dl className="profile-details"><div><dt>Email</dt><dd>{profile.email || "Not provided"}</dd></div><div><dt>Account ID</dt><dd>{profile.id || "Not provided"}</dd></div><div><dt>Location</dt><dd>{profile.location?.trim() || "Not provided"}</dd></div></dl></Card><Card><div className="card-heading"><div><p className="eyebrow">Preferences</p><h2>Language and units</h2></div></div><form className="farm-form" onSubmit={saveProfile}><label htmlFor="preferred-language">Preferred language<select id="preferred-language" className="profile-select" required value={preferredLanguage} onChange={(event) => { setPreferredLanguage(event.target.value); setSaveSuccess(false); }} disabled={saving}><option value="" disabled>Select a language</option>{preferredLanguage && !["mr", "hi", "en"].includes(preferredLanguage) && <option value={preferredLanguage}>{preferredLanguage}</option>}<option value="mr">मराठी</option><option value="hi">हिन्दी</option><option value="en">English</option></select></label><label htmlFor="preferred-units">Preferred units<select id="preferred-units" className="profile-select" required value={preferredUnits} onChange={(event) => { setPreferredUnits(event.target.value); setSaveSuccess(false); }} disabled={saving}><option value="" disabled>Select units</option>{preferredUnits && !["metric", "imperial"].includes(preferredUnits) && <option value={preferredUnits}>{preferredUnits}</option>}<option value="metric">Metric</option><option value="imperial">Imperial</option></select></label>{loadError && <p className="form-error" role="alert">{loadError}</p>}{saveError && <p className="form-error" role="alert">{saveError}</p>}{saveSuccess && <p className="form-success" role="status">Your preferences were saved.</p>}<button className="primary-button" disabled={saving || loading}>{saving ? "Saving…" : "Save preferences"}</button></form></Card></>}</div>;
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
        temperatureCelsius: current.temperature_celsius,
        condition: current.condition,
        rainfallMm: current.rainfall_mm,
        humidityPercent: current.humidity_percent,
        windSpeedKph: current.wind_speed_kph,
        pressureHpa: current.pressure_hpa,
        observedAt: current.observed_at
      }
    : null;
  return <div className="page"><header className="page-header"><div><p className="eyebrow">OpenWeather</p><h1>Weather</h1><p>Current conditions and forecast for your first saved farm.</p></div></header>{state.loading && <LoadingState label="Loading live weather…" />}{state.error && <ErrorState message={state.error} retry={state.refresh} />}{weather && state.data && <div className="content-grid"><WeatherCard weather={weather} /><ForecastCard items={state.data.daily.map((item) => ({ forecastFor: item.forecast_for, temperatureMinCelsius: item.temperature_min_celsius, temperatureMaxCelsius: item.temperature_max_celsius, precipitationMm: item.precipitation_mm, rainProbabilityPercent: item.rain_probability_percent }))} /></div>}</div>;
}

export function RecommendationsPage() {
  const state = useResource(weatherGptApi.getRecommendations);
  const data = state.data;
  return <div className="page"><header className="page-header"><div><p className="eyebrow">Decision support</p><h1>Agricultural recommendations</h1><p>Current decisions from configured rules and your farm’s available weather data. Results are not saved as recommendations.</p></div></header>{state.loading && <LoadingState />}{state.error && <ErrorState message={state.error} retry={state.refresh} />}{!state.loading && !state.error && data && <>{data.message && <Card><p role="status">{data.message}</p>{data.farms.length === 0 && <a className="secondary-button" href="/farms">Add a farm</a>}</Card>}{data.farms.map((farm) => <Card key={farm.farmId}><div className="card-heading"><div><p className="eyebrow">{farm.weatherProvider} · weather fetched {new Date(farm.weatherFetchedAt).toLocaleString()}</p><h2>{farm.farmName}</h2></div></div><div className="stack">{farm.recommendations.map((item) => <article key={item.id} className={`recommendation-card recommendation-${item.status}`}><span className="recommendation-check" aria-hidden="true">{item.status === "available" ? "✓" : "!"}</span><div><p className="eyebrow">{item.recommendationType.replaceAll("_", " ")}{item.cropName ? ` · ${item.cropName}` : " · Farm-wide"}</p><h3>{item.status === "available" ? item.decision : "Additional inputs required"}</h3>{item.status === "available" && <p>Rule risk: {item.riskLevel} · Confidence: {Math.round(item.confidence * 100)}%</p>}<ul>{item.reasons.map((reason, index) => <li key={`${item.id}-${index}`}>{reason}</li>)}</ul></div></article>)}</div></Card>)}{data.farms.length > 0 && data.status === "available" && <Card><p>These results are computed from the latest available farm weather and configured deterministic rules. They are not stored as historical recommendations.</p></Card>}</>}</div>;
}

export function AlertsPage() {
  const state = useResource(weatherGptApi.getAlerts);
  return <div className="page"><header className="page-header"><div><p className="eyebrow">Safety first</p><h1>Weather alerts</h1><p>Important weather risks for your farm will appear here.</p></div></header><Card>{state.loading ? <LoadingState /> : state.error ? <ErrorState message={state.error} retry={state.refresh} /> : state.data?.length ? <div className="stack">{state.data.map((item) => <AlertCard key={item.id} alert={item} />)}</div> : <EmptyState title="No active alerts" description="There are no active, unacknowledged weather alerts for your farms." />}</Card></div>;
}

export function AuthPage({ mode }: { mode: "login" | "register" }) {
  const navigate = useNavigate();
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
      storeAccessToken(response.access_token);
      navigate("/dashboard", { replace: true });
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to continue."); } finally { setSubmitting(false); }
  };
  return <main className="auth-page"><section className="auth-intro"><span>🌱</span><h1>WeatherGPT</h1><p>Clear, practical weather support for your farm.</p></section><section className="auth-card"><p className="eyebrow">Welcome</p><h2>{isRegister ? "Create your farmer account" : "Sign in to your account"}</h2><form onSubmit={submit}>{isRegister && <label>Name<input name="name" required autoComplete="name" /></label>}<label>Email<input name="email" required type="email" autoComplete="email" /></label><label>Password<input name="password" required type="password" minLength={8} autoComplete={isRegister ? "new-password" : "current-password"} /></label>{error && <p className="form-error" role="alert">{error}</p>}<button className="primary-button" disabled={submitting}>{submitting ? "Please wait…" : isRegister ? "Create account" : "Sign in"}</button></form><p>{isRegister ? "Already have an account?" : "New to WeatherGPT?"} <a href={isRegister ? "/login" : "/register"}>{isRegister ? "Sign in" : "Create an account"}</a></p></section></main>;
}
