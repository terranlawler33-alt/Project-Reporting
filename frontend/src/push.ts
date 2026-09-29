import { Platform } from "react-native";
import * as Notifications from "expo-notifications";
import { apiRequest } from "@/src/api";

export async function registerForPush(user_id: string) {
  if (Platform.OS === "web") return;
  try {
    const { status } = await Notifications.requestPermissionsAsync();
    if (status !== "granted") return;
    const tokenResp = await Notifications.getDevicePushTokenAsync();
    await apiRequest("/register-push", {
      method: "POST",
      body: JSON.stringify({
        user_id,
        platform: Platform.OS,
        device_token: tokenResp.data,
      }),
    });
  } catch {
    // Non-blocking
  }
}
