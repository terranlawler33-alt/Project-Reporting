import { useEffect, useState } from "react";
import { Tabs } from "expo-router";
import { View, Text, StyleSheet } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { colors } from "@/src/theme";
import { Platform } from "react-native";
import { api } from "@/src/api";

export default function TabsLayout() {
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    let alive = true;
    const refresh = async () => {
      try {
        const { count } = await api.unreadResponseCount();
        if (alive) setUnread(count || 0);
      } catch {}
    };
    refresh();
    const t = setInterval(refresh, 20000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.brandPrimary,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: {
          backgroundColor: colors.surfaceSecondary,
          borderTopColor: colors.border,
          ...(Platform.OS === "web" ? { height: 64 } : {}),
        },
        tabBarItemStyle: { alignSelf: "center" },
        tabBarLabelStyle: { fontSize: 11, fontWeight: "600" },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Home",
          tabBarIcon: ({ color, size }) => <Ionicons name="home" size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="reports"
        options={{
          title: "Reports",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="document-text" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="mail"
        options={{
          title: "Mail",
          tabBarIcon: ({ color, size }) => (
            <View>
              <Ionicons name="mail" size={size} color={color} />
              {unread > 0 ? (
                <View style={styles.badge} testID="mail-tab-badge">
                  <Text style={styles.badgeText}>{unread > 99 ? "99+" : unread}</Text>
                </View>
              ) : null}
            </View>
          ),
        }}
      />
      <Tabs.Screen
        name="map"
        options={{
          title: "Map",
          tabBarIcon: ({ color, size }) => <Ionicons name="location" size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: "Profile",
          tabBarIcon: ({ color, size }) => <Ionicons name="person-circle" size={size} color={color} />,
        }}
      />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  badge: {
    position: "absolute",
    top: -4,
    right: -8,
    backgroundColor: colors.error,
    borderRadius: 999,
    paddingHorizontal: 5,
    minWidth: 16,
    height: 16,
    alignItems: "center",
    justifyContent: "center",
  },
  badgeText: {
    color: "#fff",
    fontSize: 10,
    fontWeight: "800",
  },
});
