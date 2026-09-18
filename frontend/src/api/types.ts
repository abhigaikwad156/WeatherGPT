export type AlertSeverity = "low" | "medium" | "high" | "critical";

export interface WeatherSummary {
  temperatureCelsius: number;
  condition: string;
  rainfallMm: number;
  observedAt: string;
}

export interface ForecastItem {
  forecastFor: string;
  temperatureMinCelsius: number | null;
  temperatureMaxCelsius: number | null;
  precipitationMm: number | null;
  rainProbabilityPercent: number | null;
}

export interface AlertItem {
  id: string;
  title: string;
  body: string;
  severity: AlertSeverity;
  startsAt: string;
}

export interface RecommendationItem {
  id: string;
  recommendationType: string;
  status: "available" | "needs_input" | "not_available";
  summary: string;
  decisionVersion: string;
}

export interface DashboardData {
  currentWeather: WeatherSummary | null;
  forecast: ForecastItem[];
  activeAlerts: AlertItem[];
  currentCrop: { name: string; growthStage: string | null } | null;
  recommendedActions: RecommendationItem[];
  upcomingRisks: AlertItem[];
}

export interface Farm {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  area_hectares: number | null;
  soil_type: string | null;
  irrigation_type: string | null;
  soil_moisture_percent: number | null;
}

export interface CurrentLocation {
  latitude: number | string;
  longitude: number | string;
  accuracy_meters: number | string | null;
  updated_at: string;
  location_name?: string | null;
}

export interface FarmLocation {
  latitude: number | string;
  longitude: number | string;
  accuracy_meters: number | string | null;
  location_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface Crop {
  id: string;
  farm_id: string;
  name: string;
  variety: string | null;
  sowing_date: string | null;
  growth_stage: string | null;
  is_active: boolean;
}

export interface FarmWeather {
  farm_id: string;
  provider: string;
  fetched_at: string;
  current: {
    observed_at: string;
    temperature_celsius: number | null;
    humidity_percent: number | null;
    rainfall_mm: number | null;
    wind_speed_kph: number | null;
    condition: string | null;
  } | null;
  hourly: Array<{
    observed_at: string;
    temperature_celsius: number | null;
    humidity_percent: number | null;
    rainfall_mm: number | null;
    wind_speed_kph: number | null;
    condition: string | null;
  }>;
  daily: Array<{
    forecast_for: string;
    temperature_min_celsius: number | null;
    temperature_max_celsius: number | null;
    precipitation_mm: number | null;
    rain_probability_percent: number | null;
    condition: string | null;
  }>;
  severe: Array<{
    title: string;
    description: string;
    severity: string;
    starts_at: string;
    ends_at: string | null;
  }>;
}

export interface ChatCard {
  type: "recommendation" | "weather" | "alert";
  recommendation?: RecommendationItem;
  weather?: WeatherSummary;
  alert?: AlertItem;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  createdAt: string;
  cards?: ChatCard[];
  metadata?: {
    intent: string;
    agricultural?: {
      decisionType: string;
      decision: string;
      riskLevel: string;
      confidence: number;
      reasons: string[];
      deterministic: boolean;
      citations: Array<Record<string, unknown>>;
    };
  };
}

export interface ChatResponse {
  conversationId: string;
  message: ChatMessage;
}
