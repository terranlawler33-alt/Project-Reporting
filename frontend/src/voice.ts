import { Platform } from "react-native";
import { getToken } from "@/src/auth/storage";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL!;

/**
 * Upload an audio file URI to /api/transcribe using multipart/form-data.
 * Works on iOS/Android (file URI) and web (blob URL).
 */
export async function transcribeAudio(uri: string, mimeType = "audio/m4a"): Promise<string> {
  const token = await getToken();
  const form = new FormData();

  if (Platform.OS === "web") {
    const res = await fetch(uri);
    const blob = await res.blob();
    const ext = (blob.type.split("/")[1] || "webm").split(";")[0];
    form.append("audio", blob, `recording.${ext}`);
  } else {
    form.append("audio", {
      uri,
      name: "recording.m4a",
      type: mimeType,
    } as any);
  }

  const r = await fetch(`${BASE}/api/transcribe`, {
    method: "POST",
    body: form,
    headers: {
      Accept: "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (!r.ok) {
    const txt = await r.text();
    throw new Error(txt || "Transcription failed");
  }
  const data = await r.json();
  return (data?.text || "").trim();
}
