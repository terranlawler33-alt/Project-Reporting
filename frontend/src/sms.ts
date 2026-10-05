import { Platform, PermissionsAndroid, Linking } from "react-native";

export type DeviceSms = {
  id: string; // local phone id (not uuid) — stringified
  address: string; // phone number
  body: string;
  date: number; // epoch ms
  type: number; // 1 inbox, 2 sent
  display_name?: string;
};

export const isSmsAvailable = (): boolean => Platform.OS === "android";

/**
 * Request Android READ_SMS at runtime (manifest permission already declared).
 * Returns true if granted. Caller should guide the user to Settings when denied+!canAskAgain.
 */
export async function requestSmsPermission(): Promise<{
  granted: boolean;
  canAskAgain: boolean;
}> {
  if (Platform.OS !== "android") return { granted: false, canAskAgain: false };
  try {
    const result = await PermissionsAndroid.request(
      PermissionsAndroid.PERMISSIONS.READ_SMS,
      {
        title: "Allow access to SMS",
        message:
          "Summar-Eeze lets you pull job-site texts into your daily report. We only read messages when you tap Import.",
        buttonPositive: "Allow",
        buttonNegative: "Not now",
      },
    );
    if (result === PermissionsAndroid.RESULTS.GRANTED) {
      return { granted: true, canAskAgain: true };
    }
    if (result === PermissionsAndroid.RESULTS.NEVER_ASK_AGAIN) {
      return { granted: false, canAskAgain: false };
    }
    return { granted: false, canAskAgain: true };
  } catch {
    return { granted: false, canAskAgain: true };
  }
}

/**
 * Fetch inbox SMS from the device for the last N days.
 * Only works on Android; returns [] on other platforms.
 */
export async function fetchRecentSms(days = 7, maxCount = 200): Promise<DeviceSms[]> {
  if (Platform.OS !== "android") return [];

  let SmsAndroid: any;
  try {
    // Dynamic require so metro doesn't try to resolve it on iOS/web
    SmsAndroid = require("react-native-get-sms-android");
  } catch {
    return [];
  }
  if (!SmsAndroid?.list) return [];

  const since = Date.now() - days * 24 * 60 * 60 * 1000;
  const filter = {
    box: "inbox",
    minDate: since,
    maxCount,
    indexFrom: 0,
  };

  return new Promise<DeviceSms[]>((resolve) => {
    try {
      SmsAndroid.list(
        JSON.stringify(filter),
        () => resolve([]),
        (count: number, smsList: string) => {
          try {
            const parsed = JSON.parse(smsList);
            const items: DeviceSms[] = (parsed || []).map((m: any) => ({
              id: String(m._id ?? m.id ?? m.date),
              address: String(m.address ?? ""),
              body: String(m.body ?? ""),
              date: Number(m.date ?? Date.now()),
              type: Number(m.type ?? 1),
              display_name: m.display_name,
            }));
            resolve(items);
          } catch {
            resolve([]);
          }
        },
      );
    } catch {
      resolve([]);
    }
  });
}

export const openAppSettings = () => {
  if (Platform.OS === "android") {
    Linking.openSettings().catch(() => {});
  } else if (Platform.OS === "ios") {
    Linking.openURL("app-settings:").catch(() => {});
  }
};
