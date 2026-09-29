import { useEffect, useState, useCallback } from "react";
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  Pressable,
  RefreshControl,
  ActivityIndicator,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Location from "expo-location";
import Ionicons from "@react-native-vector-icons/ionicons";
import * as Haptics from "expo-haptics";
import { useRouter, useFocusEffect } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { Image } from "expo-image";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth/AuthProvider";
import { colors, spacing, radius } from "@/src/theme";

const WEATHER_HERO_IMG =
  "https://images.unsplash.com/photo-1505533542167-8c89838bb19e?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA2MjJ8MHwxfHNlYXJjaHwxfHxhYnN0cmFjdCUyMG1vcm5pbmclMjBsaWdodCUyMHNreSUyMHdlYXRoZXIlMjBiYWNrZ3JvdW5kfGVufDB8fHx8MTc5MDY1MTk5NHww&ixlib=rb-4.1.0&q=85";

export default function HomeScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const [weather, setWeather] = useState<any>(null);
  const [loadingWeather, setLoadingWeather] = useState(false);
  const [visits, setVisits] = useState<any[]>([]);
  const [breaks, setBreaks] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const loadEverything = useCallback(async () => {
    if (!user) return;
    try {
      let coords: { latitude: number; longitude: number } | null = null;
      try {
        const { status } = await Location.requestForegroundPermissionsAsync();
        if (status === "granted") {
          setLoadingWeather(true);
          const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
          coords = { latitude: pos.coords.latitude, longitude: pos.coords.longitude };
        } else {
          coords = { latitude: 40.7128, longitude: -74.006 };
        }
      } catch {
        coords = { latitude: 40.7128, longitude: -74.006 };
      }
      if (coords) {
        try {
          const w = await api.weather(coords.latitude, coords.longitude);
          setWeather(w);
        } catch {}
      }
      try {
        const [v, b] = await Promise.all([api.visitsToday(), api.breaksToday()]);
        setVisits(v);
        setBreaks(b);
      } catch {}
    } finally {
      setLoadingWeather(false);
    }
  }, [user]);

  useEffect(() => {
    if (user) loadEverything();
  }, [user, loadEverything]);

  useFocusEffect(
    useCallback(() => {
      if (user) loadEverything();
    }, [user, loadEverything]),
  );

  const activeBreak = breaks.find((b) => !b.ended_at);

  const onStartDay = async () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    router.push("/(tabs)/map");
  };

  const onAddBreak = async () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    router.push("/break-modal");
  };

  const onEndDay = async () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    router.push("/(tabs)/reports");
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView
        contentContainerStyle={{ paddingBottom: spacing.xxl }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => {
          setRefreshing(true);
          await loadEverything();
          setRefreshing(false);
        }} tintColor={colors.brandPrimary} />}
      >
        {/* Weather Hero */}
        <View style={[styles.hero, { paddingTop: insets.top + spacing.lg }]}>
          <Image source={{ uri: WEATHER_HERO_IMG }} style={StyleSheet.absoluteFill} contentFit="cover" />
          <LinearGradient
            colors={["rgba(17,24,39,0.15)", "rgba(17,24,39,0.75)"]}
            style={StyleSheet.absoluteFill}
          />
          <View style={styles.heroInner}>
            <Text style={styles.heroGreeting}>Good day,</Text>
            <Text style={styles.heroName} testID="home-user-name">
              {user?.name || "Team"}
            </Text>
            <View style={styles.weatherRow}>
              {loadingWeather ? (
                <ActivityIndicator color="#fff" />
              ) : weather ? (
                <>
                  <Ionicons name="partly-sunny" size={28} color="#fff" />
                  <Text style={styles.weatherTemp} testID="home-weather-temp">
                    {Math.round(weather.temperature_f)}°F
                  </Text>
                  <View style={styles.weatherMeta}>
                    <Text style={styles.weatherCond}>{weather.conditions}</Text>
                    <Text style={styles.weatherSub}>
                      Wind {Math.round(weather.wind_mph || 0)} mph · Precip{" "}
                      {(weather.precipitation || 0).toFixed(2)} in
                    </Text>
                  </View>
                </>
              ) : (
                <Text style={styles.weatherCond}>Weather unavailable</Text>
              )}
            </View>
          </View>
        </View>

        {/* Quick Actions */}
        <View style={styles.actionsRow}>
          <ActionButton
            testID="start-day-action"
            icon="play-circle"
            label="Start Day"
            onPress={onStartDay}
          />
          <ActionButton
            testID="add-break-action"
            icon="pause-circle"
            label="Add Break"
            onPress={onAddBreak}
            highlight={!!activeBreak}
          />
          <ActionButton
            testID="end-day-action"
            icon="stop-circle"
            label="End Day"
            onPress={onEndDay}
          />
        </View>

        {activeBreak ? (
          <View style={styles.activeBreak} testID="active-break-banner">
            <Ionicons name="alert-circle" size={20} color={colors.warning} />
            <Text style={styles.activeBreakText}>
              On {activeBreak.break_type} break — {activeBreak.reason || "no reason set"}
            </Text>
            <Pressable
              testID="end-break-button"
              onPress={async () => {
                await api.endBreak(activeBreak.id);
                await loadEverything();
              }}
              style={styles.endBreakBtn}
            >
              <Text style={styles.endBreakBtnText}>End</Text>
            </Pressable>
          </View>
        ) : null}

        {/* Today's Plan */}
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Today's Activity</Text>
            <Text style={styles.sectionSub}>
              {visits.length} visits · {breaks.length} breaks
            </Text>
          </View>
          {visits.length === 0 ? (
            <View style={styles.emptyCard}>
              <Ionicons name="map-outline" size={28} color={colors.muted} />
              <Text style={styles.emptyText}>No site visits yet today</Text>
              <Text style={styles.emptySub}>Head to Map to check in at a job site.</Text>
            </View>
          ) : (
            visits.map((v) => (
              <View key={v.id} style={styles.visitCard} testID={`visit-card-${v.id}`}>
                <View style={styles.visitIcon}>
                  <Ionicons name="location" size={18} color={colors.brandPrimary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.visitTitle}>
                    {v.customer_name || "Job Site"} {v.project_code ? `· ${v.project_code}` : ""}
                  </Text>
                  <Text style={styles.visitSub}>
                    {v.address || `${v.latitude.toFixed(4)}, ${v.longitude.toFixed(4)}`}
                  </Text>
                  {v.notes ? <Text style={styles.visitNotes}>{v.notes}</Text> : null}
                </View>
              </View>
            ))
          )}
        </View>
      </ScrollView>
    </View>
  );
}

function ActionButton({
  icon,
  label,
  onPress,
  testID,
  highlight,
}: {
  icon: any;
  label: string;
  onPress: () => void;
  testID: string;
  highlight?: boolean;
}) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      style={({ pressed }) => [
        styles.actionBtn,
        highlight && styles.actionBtnHighlight,
        pressed && { opacity: 0.85 },
      ]}
    >
      <Ionicons
        name={icon}
        size={26}
        color={highlight ? colors.onBrandPrimary : colors.brandPrimary}
      />
      <Text
        style={[
          styles.actionLabel,
          highlight && { color: colors.onBrandPrimary },
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  hero: {
    minHeight: 220,
    justifyContent: "flex-end",
    overflow: "hidden",
    borderBottomLeftRadius: radius.lg,
    borderBottomRightRadius: radius.lg,
  },
  heroInner: { padding: spacing.lg },
  heroGreeting: { color: "rgba(255,255,255,0.8)", fontSize: 13 },
  heroName: { color: "#fff", fontSize: 22, fontWeight: "700", marginBottom: spacing.md },
  weatherRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  weatherTemp: { color: "#fff", fontSize: 32, fontWeight: "800" },
  weatherMeta: { flex: 1 },
  weatherCond: { color: "#fff", fontSize: 15, fontWeight: "600" },
  weatherSub: { color: "rgba(255,255,255,0.75)", fontSize: 12 },
  actionsRow: {
    flexDirection: "row",
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    marginTop: spacing.lg,
  },
  actionBtn: {
    flex: 1,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    padding: spacing.md,
    alignItems: "center",
    borderWidth: 1,
    borderColor: colors.border,
    gap: spacing.xs,
  },
  actionBtnHighlight: {
    backgroundColor: colors.brandPrimary,
    borderColor: colors.brandPrimary,
  },
  actionLabel: {
    color: colors.onSurface,
    fontSize: 12,
    fontWeight: "600",
  },
  activeBreak: {
    marginHorizontal: spacing.lg,
    marginTop: spacing.md,
    padding: spacing.md,
    backgroundColor: colors.brandTertiary,
    borderRadius: radius.md,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
  },
  activeBreakText: { flex: 1, color: colors.onBrandTertiary, fontSize: 13, fontWeight: "600" },
  endBreakBtn: {
    backgroundColor: colors.onBrandTertiary,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
  },
  endBreakBtnText: { color: colors.brandTertiary, fontWeight: "700", fontSize: 12 },
  section: { padding: spacing.lg },
  sectionHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: spacing.md,
  },
  sectionTitle: { fontSize: 18, fontWeight: "700", color: colors.onSurface },
  sectionSub: { color: colors.muted, fontSize: 12 },
  emptyCard: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    padding: spacing.xl,
    alignItems: "center",
    borderWidth: 1,
    borderColor: colors.border,
  },
  emptyText: { color: colors.onSurface, fontWeight: "600", marginTop: spacing.sm },
  emptySub: { color: colors.muted, fontSize: 12, marginTop: spacing.xs },
  visitCard: {
    flexDirection: "row",
    gap: spacing.md,
    padding: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.sm,
    alignItems: "flex-start",
  },
  visitIcon: {
    width: 36,
    height: 36,
    borderRadius: radius.md,
    backgroundColor: colors.brandTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
  visitTitle: { fontWeight: "700", color: colors.onSurface, fontSize: 14 },
  visitSub: { color: colors.muted, fontSize: 12, marginTop: 2 },
  visitNotes: { color: colors.onSurfaceTertiary, fontSize: 12, marginTop: 4, fontStyle: "italic" },
});
