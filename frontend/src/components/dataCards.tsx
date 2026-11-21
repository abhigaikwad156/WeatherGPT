import type { AlertItem, ForecastItem, RecommendationItem, WeatherSummary } from "../api/types";
import { Card, EmptyState, SeverityBadge } from "./ui";

function weatherIcon(condition: string | undefined, rainProbability?: number | null) {
  const value = (condition ?? "").toLowerCase();
  if (rainProbability != null && rainProbability >= 50) return "🌧️";
  if (value.includes("storm") || value.includes("thunder")) return "⛈️";
  if (value.includes("rain")) return "🌦️";
  if (value.includes("cloud")) return "⛅";
  return "☀️";
}

export function WeatherCard({ weather }: { weather: WeatherSummary }) {
  const metric = (value: number | null, unit: string) => value == null ? "—" : `${value} ${unit}`;
  return <Card className="weather-card"><div className="card-heading"><div><p className="eyebrow">आजचे वातावरण  · Today</p><h2>{new Date().toLocaleDateString([], { weekday: "long" })}</h2></div><span className="weather-location">⌖ Farm</span></div><div className="weather-main"><span className="weather-icon" aria-label={weather.condition ?? undefined}>{weatherIcon(weather.condition ?? undefined)}</span><div><strong>{weather.temperatureCelsius ?? "—"}</strong>{weather.temperatureCelsius != null && <span className="temperature-unit">C</span>}<p>{weather.condition || "Weather condition not available"}</p></div></div><div className="weather-metrics"><span><b>💧</b><small>Humidity</small><strong>{metric(weather.humidityPercent, "%")}</strong></span><span><b>🌧️</b><small>Rainfall</small><strong>{metric(weather.rainfallMm, "mm")}</strong></span><span><b>💨</b><small>Wind</small><strong>{metric(weather.windSpeedKph, "km/h")}</strong></span><span><b>◌</b><small>Pressure</small><strong>{metric(weather.pressureHpa, "hPa")}</strong></span></div></Card>;
}

export function ForecastCard({ items }: { items: ForecastItem[] }) {
  return <Card><div className="card-heading"><div><p className="eyebrow">पाऊस · Rain forecast</p><h2>Will it rain?</h2></div><a href="/weather" className="text-link">See full forecast →</a></div>{items.length === 0 ? <EmptyState title="No forecast yet" description="Rain information will appear when weather data is available." /> : <div className="forecast-list">{items.slice(0, 5).map((item, index) => <div key={item.forecastFor} className={`forecast-item ${index === 0 ? "today" : ""}`}><strong>{index === 0 ? "Today" : new Date(item.forecastFor).toLocaleDateString([], { weekday: "short" })}</strong><span>{weatherIcon(undefined, item.rainProbabilityPercent)}</span><span><b>{item.temperatureMaxCelsius ?? "–"}°</b> <small>{item.temperatureMinCelsius ?? "–"}°</small></span><span className="rain-chance"><i>💧</i> {item.rainProbabilityPercent ?? "–"}%</span></div>)}</div>}</Card>;
}

export function AlertCard({ alert }: { alert: AlertItem }) {
  return <article className="alert-card"><div><SeverityBadge severity={alert.severity} /><h3>{alert.title}</h3></div><p>{alert.body}</p><small>{new Date(alert.startsAt).toLocaleString()}</small></article>;
}

export function RecommendationCard({ recommendation }: { recommendation: RecommendationItem }) {
  const status = recommendation.decision === "NEEDS_INPUT"
    ? "Need more farm information"
    : recommendation.decision
      ? "Rule-based decision"
    : recommendation.status === "available"
      ? "Do this today"
      : recommendation.status === "needs_input"
        ? "Need more farm information"
        : "Not available yet";
  const missingInputLabels: Record<string, string> = {
    crop_age_days: "crop age (planting date)",
    growth_stage: "recorded growth stage",
    reviewed_soil_moisture_threshold: "agronomist-reviewed soil-moisture threshold",
    reviewed_forecast_rainfall_threshold: "agronomist-reviewed forecast-rainfall threshold",
    soil_moisture_percent: "soil-moisture reading",
    soil_moisture_measured_at: "soil-moisture measurement time",
    fresh_soil_moisture_measurement: "fresh soil-moisture reading",
    forecast_rainfall_mm: "complete forecast rainfall data",
    forecast_horizon_days: "matching forecast period",
    local_agronomist_review: "Maharashtra agronomist review",
    approved_irrigation_profile: "approved irrigation profile",
    approved_irrigation_schedule: "approved irrigation schedule",
    approved_irrigation_rule: "approved irrigation rule",
    irrigation_layout: "drip irrigation layout",
    last_irrigated_at: "last irrigation date",
    reviewed_source: "current reviewed source"
  };
  const missingInputs = recommendation.missingInputs?.map(
    (input) => missingInputLabels[input] ?? input.replaceAll("_", " ").replace("irrigation configuration.", "")
  );
  return <article className={`recommendation-card recommendation-${recommendation.status}`}><span className="recommendation-check" aria-hidden="true">{recommendation.status === "available" ? "✓" : "!"}</span><div><p className="eyebrow">{recommendation.recommendationType}</p><h3>{recommendation.summary}</h3><strong className="recommendation-status">{status}</strong>{recommendation.applicableCropStage && <p>Applicable crop stage: {recommendation.applicableCropStage}{recommendation.cropAgeDays != null ? ` · ${recommendation.cropAgeDays} days after planting` : ""}</p>}{recommendation.explanations?.en && <p>{recommendation.explanations.en}</p>}{recommendation.explanations?.mr && <p lang="mr">{recommendation.explanations.mr}</p>}{missingInputs && missingInputs.length > 0 && <p>Missing: {missingInputs.join(", ")}</p>}{recommendation.dataBasis && <p>Decision basis: {recommendation.dataBasis.replaceAll("_", " ")}{recommendation.scheduleIntervalDays ? ` · ${recommendation.scheduleIntervalDays}-day source schedule` : ""}</p>}{recommendation.weatherLimitations?.map((limitation) => <p key={limitation}>{limitation}</p>)}{recommendation.source?.sourceUri && <p>Source: <a href={recommendation.source.sourceUri} target="_blank" rel="noreferrer">{recommendation.source.documentTitle ?? recommendation.source.publisher ?? "Agricultural guidance"}</a>{recommendation.source.pageOrSection && ` · ${recommendation.source.pageOrSection}`}{recommendation.source.sourceRegion && ` · ${recommendation.source.sourceRegion}`}{recommendation.source.reviewStatus && ` · ${recommendation.source.reviewStatus.replaceAll("_", " ")}`}</p>}{recommendation.evidence?.map((evidence, index) => <p key={`${evidence.source.sourceUri}-${index}`}>Evidence: {evidence.claim} <a href={evidence.source.sourceUri ?? undefined} target="_blank" rel="noreferrer">{evidence.source.documentTitle ?? evidence.source.publisher ?? "Source"}</a>{evidence.source.reviewStatus && ` · ${evidence.source.reviewStatus.replaceAll("_", " ")}`}</p>)}</div></article>;
}
