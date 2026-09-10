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
  return <Card className="weather-card"><div className="card-heading"><div><p className="eyebrow">आज का मौसम · Today</p><h2>{new Date().toLocaleDateString([], { weekday: "long" })}</h2></div><span className="weather-location">⌖ Farm</span></div><div className="weather-main"><span className="weather-icon" aria-label={weather.condition}>{weatherIcon(weather.condition)}</span><div><strong>{weather.temperatureCelsius}°</strong><span className="temperature-unit">C</span><p>{weather.condition || "Weather condition not available"}</p></div></div><div className="weather-metrics"><span><b>💧</b><small>Humidity</small><strong>—</strong></span><span><b>🌧️</b><small>Rainfall</small><strong>{weather.rainfallMm ?? "—"} mm</strong></span><span><b>💨</b><small>Wind</small><strong>—</strong></span></div></Card>;
}

export function ForecastCard({ items }: { items: ForecastItem[] }) {
  return <Card><div className="card-heading"><div><p className="eyebrow">पाऊस · Rain forecast</p><h2>Will it rain?</h2></div><a href="/weather" className="text-link">See full forecast →</a></div>{items.length === 0 ? <EmptyState title="No forecast yet" description="Rain information will appear when weather data is available." /> : <div className="forecast-list">{items.slice(0, 5).map((item, index) => <div key={item.forecastFor} className={`forecast-item ${index === 0 ? "today" : ""}`}><strong>{index === 0 ? "Today" : new Date(item.forecastFor).toLocaleDateString([], { weekday: "short" })}</strong><span>{weatherIcon(undefined, item.rainProbabilityPercent)}</span><span><b>{item.temperatureMaxCelsius ?? "–"}°</b> <small>{item.temperatureMinCelsius ?? "–"}°</small></span><span className="rain-chance"><i>💧</i> {item.rainProbabilityPercent ?? "–"}%</span></div>)}</div>}</Card>;
}

export function AlertCard({ alert }: { alert: AlertItem }) {
  return <article className="alert-card"><div><SeverityBadge severity={alert.severity} /><h3>{alert.title}</h3></div><p>{alert.body}</p><small>{new Date(alert.startsAt).toLocaleString()}</small></article>;
}

export function RecommendationCard({ recommendation }: { recommendation: RecommendationItem }) {
  const status = recommendation.status === "available" ? "Do this today" : recommendation.status === "needs_input" ? "Need more farm information" : "Not available yet";
  return <article className={`recommendation-card recommendation-${recommendation.status}`}><span className="recommendation-check" aria-hidden="true">{recommendation.status === "available" ? "✓" : "!"}</span><div><p className="eyebrow">{recommendation.recommendationType}</p><h3>{recommendation.summary}</h3><strong className="recommendation-status">{status}</strong></div></article>;
}
