import { request } from "./client";
import type {
  ChatResponse,
  Crop,
  CurrentLocation,
  DashboardData,
  Farm,
  FarmLocation,
  FarmWeather
} from "./types";

export interface AuthTokenResponse {
  access_token: string;
  token_type: string;
  user: {
    id: string;
    email: string;
    display_name: string;
    preferred_language: string;
  };
}

export const weatherGptApi = {
  getDashboard: () => request<DashboardData>("/dashboard"),
  getFarms: () => request<Farm[]>("/farms"),
  getCurrentLocation: () => request<CurrentLocation>("/location/current"),
  saveCurrentLocation: (payload: { latitude: number; longitude: number; accuracy_meters?: number }) =>
    request<CurrentLocation>("/location/current", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  getFarmLocation: (farmId: string) => request<FarmLocation>(`/farms/${farmId}/location`),
  updateFarmLocation: (
    farmId: string,
    payload: {
      latitude: number;
      longitude: number;
      accuracy_meters?: number;
      location_name?: string;
    }
  ) =>
    request<FarmLocation>(`/farms/${farmId}/location`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  useCurrentLocationForFarm: (farmId: string) =>
    request<FarmLocation>(`/farms/${farmId}/location/from-current`, { method: "POST" }),
  getFarmWeather: (farmId: string) => request<FarmWeather>(`/farms/${farmId}/weather?refresh=true`),
  getFarmCrops: (farmId: string) => request<Crop[]>(`/farms/${farmId}/crops`),
  createCrop: (farmId: string, payload: { name: string; variety?: string; sowing_date?: string; growth_stage?: string }) =>
    request<Crop>(`/farms/${farmId}/crops`, { method: "POST", body: JSON.stringify(payload) }),
  createFarm: (payload: {
    name: string;
    latitude: number;
    longitude: number;
    area_hectares?: number;
    soil_type?: string;
    irrigation_type?: string;
    soil_moisture_percent?: number;
  }) => request<Farm>("/farms", { method: "POST", body: JSON.stringify(payload) }),
  getCrops: () => request<unknown>("/farmer-crops"),
  getWeather: () => request<unknown>("/weather"),
  getRecommendations: () => request<unknown>("/recommendations"),
  getAlerts: () => request<unknown>("/weather-alerts"),
  getProfile: () => request<unknown>("/users/me"),
  login: (payload: { email: string; password: string }) =>
    request<AuthTokenResponse>("/auth/login", { method: "POST", body: JSON.stringify(payload) }),
  register: (payload: { display_name: string; email: string; password: string }) =>
    request<AuthTokenResponse>("/auth/register", { method: "POST", body: JSON.stringify(payload) }),
  sendMessage: (payload: { content: string; language: string; conversationId?: string }) =>
    request<ChatResponse>("/conversations/messages", {
      method: "POST",
      body: JSON.stringify(payload)
    })
};
