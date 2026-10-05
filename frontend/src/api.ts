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
  getDraftToday: () => apiRequest<any | null>("/reports/draft/today"),
  saveDraft: (payload: any) =>
    apiRequest<any>("/reports/draft", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  submitDraft: () =>
    apiRequest<any>("/reports/draft/submit", { method: "POST" }),
  discardDraft: () =>
    apiRequest<{ ok: boolean; removed: number }>("/reports/draft", { method: "DELETE" }),
  createSmsBulk: (items: any[]) =>
    apiRequest<any[]>("/sms-logs/bulk", {
      method: "POST",
      body: JSON.stringify({ items }),
    }),
  // ---- Report Responses (Mail) ----
  listResponses: (params?: { include_archived?: boolean; unread_only?: boolean }) => {
    const q = new URLSearchParams();
    if (params?.include_archived) q.set("include_archived", "true");
    if (params?.unread_only) q.set("unread_only", "true");
    const qs = q.toString();
    return apiRequest<any[]>(`/responses${qs ? `?${qs}` : ""}`);
  },
  unreadResponseCount: () => apiRequest<{ count: number }>("/responses/unread-count"),
  listReportResponses: (report_id: string) =>
    apiRequest<any[]>(`/reports/${report_id}/responses`),
  markResponseRead: (id: string) =>
    apiRequest<any>(`/responses/${id}/read`, { method: "PATCH" }),
  markResponseUnread: (id: string) =>
    apiRequest<any>(`/responses/${id}/unread`, { method: "PATCH" }),
  archiveResponse: (id: string) =>
    apiRequest<any>(`/responses/${id}/archive`, { method: "POST" }),
  deleteResponse: (id: string) =>
    apiRequest<{ ok: boolean }>(`/responses/${id}`, { method: "DELETE" }),
  patchProjectSummary: (report_id: string, project_id: string, summary: string | null) =>
    apiRequest<any>(`/reports/${report_id}/projects/${project_id}/summary`, {
      method: "PATCH",
      body: JSON.stringify({ summary }),
    }),
  getResponseThread: (id: string) =>
    apiRequest<any[]>(`/responses/${id}/thread`),
  replyToResponse: (id: string, message: string) =>
    apiRequest<any>(`/responses/${id}/reply`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
  getMailSchedule: () => apiRequest<any>("/digest/mail-schedule"),
  setMailSchedule: (payload: { enabled: boolean; hour: number; minute: number }) =>
    apiRequest<any>("/digest/mail-schedule", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  sendMailDigestNow: () =>
    apiRequest<{ ok: boolean; emails_sent: number; owners: number; replies: number }>(
      "/digest/mail-send-now",
      { method: "POST" },
    ),
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
    apiRequest<{ audio_data_url: string; bytes: number; cached?: boolean; voice_provider?: string }>(`/reports/${report_id}/tts`, {
      method: "POST",
    }),
  listGroups: () => apiRequest<any[]>("/recipient-groups"),
  createGroup: (payload: any) =>
    apiRequest<any>("/recipient-groups", { method: "POST", body: JSON.stringify(payload) }),
  updateGroup: (id: string, payload: any) =>
    apiRequest<any>(`/recipient-groups/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteGroup: (id: string) =>
    apiRequest<{ ok: boolean }>(`/recipient-groups/${id}`, { method: "DELETE" }),
  regenerateSummary: (report_id: string) =>
    apiRequest<any>(`/reports/${report_id}/regenerate-summary`, { method: "POST" }),
  customerHistory: (name: string) =>
    apiRequest<{
      customer: any | null;
      name: string;
      visits: any[];
      reports: any[];
      photos: { path: string; visit_id: string; timestamp: string }[];
      counts: { visits: number; reports: number; photos: number };
    }>(`/customers/history?name=${encodeURIComponent(name)}`),
  parseProject: (text: string) =>
    apiRequest<{
      customer_name: string | null;
      address: string | null;
      project_code: string | null;
      project_name: string | null;
      notes: string | null;
      materials_used: string | null;
      start_time: string | null;
      end_time: string | null;
      touch_up: boolean;
      priority_flag: string | null;
    }>("/parse-project", { method: "POST", body: JSON.stringify({ text }) }),
  geocode: (q: string) =>
    apiRequest<{
      query: string;
      results: {
        id: number;
        name: string;
        admin1?: string;
        admin2?: string;
        country?: string;
        country_code?: string;
        latitude: number;
        longitude: number;
        postcodes?: string[];
        label: string;
      }[];
    }>(`/geocode?q=${encodeURIComponent(q)}`),
  weatherHourly: (lat: number, lon: number, hours = 12) =>
    apiRequest<{
      latitude: number;
      longitude: number;
      hours: number;
      utc_offset_seconds: number;
      fetched_at: string;
      points: {
        time: string | null;
        hour_label: string;
        temperature_f: number | null;
        precip_prob: number | null;
        precipitation: number | null;
        wind_mph: number | null;
        weather_code: number | null;
        conditions: string | null;
      }[];
    }>(`/weather/hourly?lat=${lat}&lon=${lon}&hours=${hours}`),
  refreshVisitWeather: (visit_id: string) =>
    apiRequest<any>(`/visits/${visit_id}/refresh-weather`, { method: "POST" }),
  patchVisit: (
    visit_id: string,
    patch: {
      customer_name?: string | null;
      address?: string | null;
      project_code?: string | null;
      notes?: string | null;
    },
  ) =>
    apiRequest<any>(`/visits/${visit_id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  deleteVisit: (visit_id: string) =>
    apiRequest<{ ok: boolean }>(`/visits/${visit_id}`, { method: "DELETE" }),
  toggleBookmark: (visit_id: string) =>
    apiRequest<any>(`/visits/${visit_id}/bookmark`, { method: "POST" }),
  listBookmarks: () => apiRequest<any[]>("/visits/bookmarked"),
  getUserLists: () =>
    apiRequest<{
      break_types: string[];
      priority_flags: { type: string; requires_reason: boolean }[];
      is_default: boolean;
    }>("/settings/lists"),
  putUserLists: (payload: {
    break_types: string[];
    priority_flags: { type: string; requires_reason: boolean }[];
  }) =>
    apiRequest<any>("/settings/lists", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  resetUserLists: () =>
    apiRequest<any>("/settings/lists/reset", { method: "POST" }),
};
