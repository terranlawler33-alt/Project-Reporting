import { useEffect, useState, useCallback, useRef } from "react";
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  Pressable,
  RefreshControl,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import * as Haptics from "expo-haptics";
import * as Network from "expo-network";
import { useRouter, useFocusEffect } from "expo-router";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth/AuthProvider";
import { colors, spacing, radius } from "@/src/theme";
import { flushQueue, pendingCount } from "@/src/offline";
import { PaintOpsMap, PaintOpsMapHandle } from "@/src/components/PaintOpsMap";
import { MultiLocationWeather } from "@/src/components/MultiLocationWeather";

export default function HomeScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const [visits, setVisits] = useState<any[]>([]);
  const [breaks, setBreaks] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [todayReports, setTodayReports] = useState<any[]>([]);
  const [pending, setPending] = useState(0);
  const [selectedVisitId, setSelectedVisitId] = useState<string | null>(null);
  const mapRef = useRef<PaintOpsMapHandle>(null);

  const selectedVisit = visits.find((v) => v.id === selectedVisitId) || null;

  const handleVisitPress = useCallback((v: any) => {
    Haptics.selectionAsync().catch(() => {});
    setSelectedVisitId(v.id);
    mapRef.current?.focusVisit(v);
  }, []);

  const loadEverything = useCallback(async () => {
    if (!user) return;
    // Try to flush offline queue on load
    try {
      const net = await Network.getNetworkStateAsync();
      if (net.isConnected) {
        await flushQueue();
      }
      setPending(await pendingCount());
    } catch {}
    try {
      const [v, b, allReports] = await Promise.all([
        api.visitsToday(),
        api.breaksToday(),
        api.listReports().catch(() => []),
      ]);
      setVisits(v);
      setBreaks(b);
      const today = new Date().toISOString().slice(0, 10);
      setTodayReports((allReports as any[]).filter((r) => r.report_date === today && !r.archived));
    } catch {}
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
        {/* Multi-location Weather Widget */}
        <MultiLocationWeather
          greetingName={user?.name || "Team"}
          topPadding={insets.top}
        />

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

        {pending > 0 ? (
          <View style={styles.offlineBanner} testID="offline-queue-banner">
            <Ionicons name="cloud-offline" size={16} color={colors.warning} />
            <Text style={styles.offlineText}>
              {pending} action{pending > 1 ? "s" : ""} queued — will sync when online
            </Text>
          </View>
        ) : null}

        {/* Today's Reports */}
        {todayReports.length > 0 ? (
          <View style={styles.section}>
            <View style={styles.sectionHeader}>
              <Text style={styles.sectionTitle}>Today's Reports</Text>
              <Text style={styles.sectionSub}>{todayReports.length} filed</Text>
            </View>
            {todayReports.map((r) => (
              <Pressable
                key={r.id}
                testID={`home-report-${r.id}`}
                onPress={() => router.push(`/report/${r.id}`)}
                style={({ pressed }) => [styles.reportRow, pressed && { opacity: 0.85 }]}
              >
                <View style={styles.reportIcon}>
                  <Ionicons name="sparkles" size={16} color={colors.onBrandTertiary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.reportTitle} numberOfLines={1}>
                    {r.project_name || r.project_code || "Daily Report"}
                  </Text>
                  <Text style={styles.reportSub} numberOfLines={2}>
                    {r.ai_summary}
                  </Text>
                </View>
                <Ionicons name="chevron-forward" size={16} color={colors.muted} />
              </Pressable>
            ))}
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

          {/* Interactive map + Today's Activity linked */}
          {visits.length > 0 ? (
            <View style={styles.mapCard} testID="home-map-container">
              <PaintOpsMap
                ref={mapRef}
                visits={visits}
                selectedId={selectedVisitId}
                onMarkerPress={(v) => setSelectedVisitId(v.id)}
              />
              <View style={styles.mapLegend}>
                <View style={styles.legendItem}>
                  <View style={[styles.legendDot, { backgroundColor: colors.brandPrimary }]} />
                  <Text style={styles.legendText}>Active</Text>
                </View>
                <View style={styles.legendItem}>
                  <View style={[styles.legendDot, { backgroundColor: colors.success }]} />
                  <Text style={styles.legendText}>Ended</Text>
                </View>
                <View style={styles.legendItem}>
                  <View style={[styles.legendDot, { backgroundColor: colors.warning }]} />
                  <Text style={styles.legendText}>Selected</Text>
                </View>
              </View>
            </View>
          ) : null}

          {selectedVisit ? (
            <View style={styles.pinDetail} testID="pin-detail-card">
              <View style={styles.pinDetailHead}>
                <View style={[styles.pinDetailIcon, selectedVisit.ended_at && { backgroundColor: colors.success }]}>
                  <Ionicons name="location" size={16} color={colors.onBrandPrimary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.pinDetailTitle} numberOfLines={1}>
                    {selectedVisit.customer_name || "Job Site"}
                    {selectedVisit.project_code ? ` · ${selectedVisit.project_code}` : ""}
                  </Text>
                  <Text style={styles.pinDetailSub} numberOfLines={2}>
                    {selectedVisit.address ||
                      `${selectedVisit.latitude.toFixed(5)}, ${selectedVisit.longitude.toFixed(5)}`}
                  </Text>
                </View>
                <Pressable
                  testID="pin-detail-close"
                  onPress={() => setSelectedVisitId(null)}
                  hitSlop={8}
                  style={styles.pinDetailClose}
                >
                  <Ionicons name="close" size={16} color={colors.onSurface} />
                </Pressable>
              </View>
              {selectedVisit.notes ? (
                <Text style={styles.pinDetailNotes}>{selectedVisit.notes}</Text>
              ) : null}
              <Text style={styles.pinDetailMeta}>
                {new Date(selectedVisit.timestamp).toLocaleTimeString()}
                {selectedVisit.ended_at
                  ? ` → ${new Date(selectedVisit.ended_at).toLocaleTimeString()}`
                  : " · active"}
              </Text>
            </View>
          ) : null}

          {visits.length === 0 ? (
            <View style={styles.emptyCard}>
              <Ionicons name="map-outline" size={28} color={colors.muted} />
              <Text style={styles.emptyText}>No site visits yet today</Text>
              <Text style={styles.emptySub}>Head to Map to check in at a job site.</Text>
            </View>
          ) : (
            visits.map((v) => {
              const isSelected = v.id === selectedVisitId;
              return (
                <Pressable
                  key={v.id}
                  testID={`visit-card-${v.id}`}
                  onPress={() => handleVisitPress(v)}
                  style={({ pressed }) => [
                    styles.visitCard,
                    pressed && { opacity: 0.85 },
                    isSelected && styles.visitCardSelected,
                  ]}
                >
                  <View
                    style={[
                      styles.visitIcon,
                      isSelected && { backgroundColor: colors.warning },
                    ]}
                  >
                    <Ionicons
                      name="location"
                      size={18}
                      color={isSelected ? colors.onWarning : colors.brandPrimary}
                    />
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
                  <Ionicons
                    name={isSelected ? "checkmark-circle" : "chevron-forward"}
                    size={16}
                    color={isSelected ? colors.warning : colors.muted}
                  />
                </Pressable>
              );
            })
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
  offlineBanner: {
    marginHorizontal: spacing.lg,
    marginTop: spacing.md,
    padding: spacing.sm,
    backgroundColor: "#FEF3C7",
    borderRadius: radius.md,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
  },
  offlineText: { color: colors.warning, fontWeight: "600", fontSize: 12, flex: 1 },
  reportRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    padding: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.sm,
  },
  reportIcon: {
    width: 32,
    height: 32,
    borderRadius: radius.md,
    backgroundColor: colors.brandTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
  reportTitle: { fontWeight: "700", color: colors.onSurface, fontSize: 14 },
  reportSub: { color: colors.muted, fontSize: 12, marginTop: 2 },
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
  visitCardSelected: {
    borderColor: colors.warning,
    backgroundColor: "#FEF3C7",
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
  mapCard: {
    height: 220,
    borderRadius: radius.md,
    overflow: "hidden",
    backgroundColor: colors.surfaceTertiary,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.md,
  },
  mapLegend: {
    position: "absolute",
    bottom: spacing.sm,
    left: spacing.sm,
    flexDirection: "row",
    gap: spacing.sm,
    backgroundColor: "rgba(255,255,255,0.9)",
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: radius.pill,
  },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 4 },
  legendDot: { width: 10, height: 10, borderRadius: 5 },
  legendText: { color: colors.onSurface, fontSize: 10, fontWeight: "600" },
  pinDetail: {
    padding: spacing.md,
    backgroundColor: "#FEF3C7",
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.warning,
    marginBottom: spacing.md,
  },
  pinDetailHead: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  pinDetailIcon: {
    width: 32,
    height: 32,
    borderRadius: radius.md,
    backgroundColor: colors.brandPrimary,
    alignItems: "center",
    justifyContent: "center",
  },
  pinDetailTitle: { fontWeight: "700", color: colors.onSurface, fontSize: 14 },
  pinDetailSub: { color: colors.onSurfaceTertiary, fontSize: 12, marginTop: 2 },
  pinDetailNotes: {
    color: colors.onSurfaceTertiary,
    fontSize: 12,
    marginTop: spacing.sm,
    fontStyle: "italic",
  },
  pinDetailMeta: { color: colors.muted, fontSize: 11, marginTop: spacing.xs },
  pinDetailClose: {
    padding: 4,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary,
  },
});
