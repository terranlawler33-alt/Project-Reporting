import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";

const KEY = "paintops_token";
const USER_KEY = "paintops_user";

export async function saveToken(token: string) {
  if (Platform.OS === "web") {
    localStorage.setItem(KEY, token);
  } else {
    await SecureStore.setItemAsync(KEY, token);
  }
}

export async function getToken(): Promise<string | null> {
  if (Platform.OS === "web") return localStorage.getItem(KEY);
  return await SecureStore.getItemAsync(KEY);
}

export async function clearToken() {
  if (Platform.OS === "web") {
    localStorage.removeItem(KEY);
    localStorage.removeItem(USER_KEY);
  } else {
    await SecureStore.deleteItemAsync(KEY);
    await SecureStore.deleteItemAsync(USER_KEY);
  }
}

export async function saveUser(user: any) {
  const s = JSON.stringify(user);
  if (Platform.OS === "web") localStorage.setItem(USER_KEY, s);
  else await SecureStore.setItemAsync(USER_KEY, s);
}

export async function getUser(): Promise<any | null> {
  const s = Platform.OS === "web" ? localStorage.getItem(USER_KEY) : await SecureStore.getItemAsync(USER_KEY);
  return s ? JSON.parse(s) : null;
}
