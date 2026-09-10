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
