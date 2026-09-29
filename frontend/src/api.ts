import { getToken, clearToken } from "./auth/storage";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL!;

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function apiRequest<T = any>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const token = await getToken();
  const headers: Record<string, string> = {
    ...(init.body ? { "Content-Type": "application/json" } : {}),
    ...((init.headers as Record<string, string>) || {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
  const res = await fetch(`${BASE}/api${path}`, { ...init, headers });
  if (res.status === 401) {
    await clearToken();
  }
  const text = await res.text();
  let data: any;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const msg = (data && (data.detail || data.message)) || `HTTP ${res.status}`;
    throw new ApiError(msg, res.status);
  }
  return data as T;
}

export const api = {
  login: (email: string, password: string) =>
    apiRequest<{ access_token: string; user: any }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => apiRequest<any>("/auth/me"),
  listUsers: () => apiRequest<any[]>("/admin/users"),
  createUser: (payload: any) =>
    apiRequest<any>("/admin/users", { method: "POST", body: JSON.stringify(payload) }),
  deleteUser: (id: string) =>
    apiRequest<{ ok: boolean }>(`/admin/users/${id}`, { method: "DELETE" }),
  weather: (lat: number, lon: number) =>
    apiRequest<any>(`/weather?lat=${lat}&lon=${lon}`),
  visitsToday: () => apiRequest<any[]>("/visits/today"),
  createVisit: (payload: any) =>
    apiRequest<any>("/visits", { method: "POST", body: JSON.stringify(payload) }),
  endVisit: (id: string) =>
    apiRequest<{ ok: boolean }>(`/visits/${id}/end`, { method: "POST" }),
  breaksToday: () => apiRequest<any[]>("/breaks/today"),
  startBreak: (payload: any) =>
    apiRequest<any>("/breaks", { method: "POST", body: JSON.stringify(payload) }),
  endBreak: (id: string) =>
    apiRequest<{ ok: boolean; duration_minutes: number }>(`/breaks/${id}/end`, {
      method: "POST",
    }),
  smsToday: () => apiRequest<any[]>("/sms-logs/today"),
  createSms: (payload: any) =>
    apiRequest<any>("/sms-logs", { method: "POST", body: JSON.stringify(payload) }),
  listReports: () => apiRequest<any[]>("/reports"),
  getReport: (id: string) => apiRequest<any>(`/reports/${id}`),
  createReport: (payload: any) =>
    apiRequest<any>("/reports", { method: "POST", body: JSON.stringify(payload) }),
};
