import { Platform } from "react-native";
import { getToken } from "@/src/auth/storage";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL!;

export async function uploadVisitPhoto(visitId: string, uri: string): Promise<string> {
  const token = await getToken();
  const form = new FormData();
  if (Platform.OS === "web") {
    const res = await fetch(uri);
    const blob = await res.blob();
    const ext = (blob.type.split("/")[1] || "jpg").split(";")[0];
    form.append("photo", blob, `photo.${ext}`);
  } else {
    const name = uri.split("/").pop() || "photo.jpg";
    const ext = (name.split(".").pop() || "jpg").toLowerCase();
    form.append("photo", { uri, name, type: `image/${ext}` } as any);
  }
  const r = await fetch(`${BASE}/api/visits/${visitId}/photos`, {
    method: "POST",
    body: form,
    headers: {
      Accept: "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (!r.ok) throw new Error(await r.text());
  const data = await r.json();
  return data.path;
}

export function photoUrl(path: string): string {
  return `${BASE}/api/files/${path}`;
}

export async function authedPhotoUrl(path: string): Promise<string> {
  // On web, images can't send Authorization header, so append token in query
  if (Platform.OS === "web") {
    const token = await getToken();
    return `${BASE}/api/files/${path}?token=${encodeURIComponent(token || "")}`;
  }
  return `${BASE}/api/files/${path}`;
}
