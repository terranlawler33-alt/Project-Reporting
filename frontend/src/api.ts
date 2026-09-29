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
  listCustomers: () => apiRequest<any[]>("/customers"),
  createCustomer: (payload: any) =>
    apiRequest<any>("/customers", { method: "POST", body: JSON.stringify(payload) }),
  deleteCustomer: (id: string) =>
    apiRequest<{ ok: boolean }>(`/customers/${id}`, { method: "DELETE" }),
  sendWeeklyDigest: (recipient_emails: string[]) =>
    apiRequest<any>("/digest/weekly", {
      method: "POST",
      body: JSON.stringify({ recipient_emails }),
    }),
  addSignature: (report_id: string, customer_name: string, signature_base64: string) =>
    apiRequest<any>(`/reports/${report_id}/signature`, {
      method: "PATCH",
      body: JSON.stringify({ customer_name, signature_base64 }),
    }),
  patchReport: (report_id: string, patch: any) =>
    apiRequest<any>(`/reports/${report_id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  archiveReport: (report_id: string) =>
    apiRequest<any>(`/reports/${report_id}/archive`, { method: "POST" }),
  unarchiveReport: (report_id: string) =>
    apiRequest<any>(`/reports/${report_id}/unarchive`, { method: "POST" }),
  deleteReport: (report_id: string) =>
    apiRequest<any>(`/reports/${report_id}`, { method: "DELETE" }),
  createPortalLink: (report_id: string) =>
    apiRequest<{ token: string }>(`/reports/${report_id}/portal-link`, { method: "POST" }),
  revokePortalLink: (report_id: string) =>
    apiRequest<{ ok: boolean }>(`/reports/${report_id}/portal-link`, { method: "DELETE" }),
  getSchedule: () => apiRequest<any>("/digest/schedule"),
  setSchedule: (payload: any) =>
    apiRequest<any>("/digest/schedule", { method: "PUT", body: JSON.stringify(payload) }),
  ttsReport: (report_id: string) =>
    apiRequest<{ audio_data_url: string; bytes: number }>(`/reports/${report_id}/tts`, {
      method: "POST",
    }),
};
