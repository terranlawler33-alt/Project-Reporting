import { useCallback, useEffect, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  RefreshControl,
  ActivityIndicator,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useRouter } from "expo-router";
import { api } from "@/src/api";
import { colors, spacing, radius } from "@/src/theme";

export default function ReportsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [reports, setReports] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.listReports();
      setReports(r);
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Text style={styles.headerTitle}>Daily Reports</Text>
        <Text style={styles.headerSub}>AI-summarized field ops</Text>
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.brandPrimary} size="large" />
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120 }}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={async () => {
                setRefreshing(true);
                await load();
                setRefreshing(false);
              }}
              tintColor={colors.brandPrimary}
            />
          }
        >
          {reports.length === 0 ? (
            <View style={styles.empty}>
              <Ionicons name="document-text-outline" size={40} color={colors.muted} />
              <Text style={styles.emptyText}>No reports yet</Text>
              <Text style={styles.emptySub}>
                Tap "Create Report" to compose your first daily summary.
              </Text>
            </View>
          ) : (
            reports.map((r) => (
              <Pressable
                key={r.id}
                testID={`report-card-${r.id}`}
                onPress={() => router.push(`/report/${r.id}`)}
                style={({ pressed }) => [styles.card, pressed && { opacity: 0.85 }]}
              >
                <View style={styles.cardTop}>
                  <View style={styles.aiTag}>
                    <Ionicons name="sparkles" size={12} color={colors.onBrandTertiary} />
                    <Text style={styles.aiTagText}>AI Summary</Text>
                  </View>
                  <Text style={styles.cardDate}>{r.report_date}</Text>
                </View>
                <Text style={styles.cardTitle} numberOfLines={1}>
                  {r.project_name || r.project_code || "Daily Report"}
                </Text>
                <Text style={styles.cardAuthor}>
                  {r.author_name} · {r.author_role}
                </Text>
                <Text style={styles.cardSummary} numberOfLines={3}>
                  {r.ai_summary}
                </Text>
                <View style={styles.cardMeta}>
                  <MetaBadge icon="location" count={r.visits?.length || 0} />
                  <MetaBadge icon="pause" count={r.breaks?.length || 0} />
                  <MetaBadge icon="chatbubble" count={r.sms_logs?.length || 0} />
                  {r.email_sent_to?.length ? (
                    <View style={styles.emailBadge}>
                      <Ionicons name="mail" size={11} color={colors.success} />
                      <Text style={styles.emailBadgeText}>
                        Emailed to {r.email_sent_to.length}
                      </Text>
                    </View>
                  ) : null}
                </View>
              </Pressable>
            ))
          )}
        </ScrollView>
      )}

      <Pressable
        testID="create-report-button"
        onPress={() => router.push("/report/new")}
        style={[
          styles.fab,
          { bottom: (insets.bottom || 0) + 80 },
        ]}
      >
        <Ionicons name="add" size={22} color={colors.onBrandPrimary} />
        <Text style={styles.fabText}>Create Report</Text>
      </Pressable>
    </View>
  );
}

function MetaBadge({ icon, count }: { icon: any; count: number }) {
  return (
    <View style={styles.metaBadge}>
      <Ionicons name={icon} size={11} color={colors.muted} />
      <Text style={styles.metaBadgeText}>{count}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
  },
  headerTitle: { fontSize: 24, fontWeight: "700", color: colors.onSurface },
  headerSub: { color: colors.muted, fontSize: 12, marginTop: 2 },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  empty: {
    padding: spacing.xxl,
    alignItems: "center",
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  emptyText: { fontWeight: "700", color: colors.onSurface, marginTop: spacing.sm },
  emptySub: { color: colors.muted, fontSize: 12, marginTop: spacing.xs, textAlign: "center" },
  card: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.md,
  },
  cardTop: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: spacing.sm,
  },
  aiTag: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    backgroundColor: colors.brandTertiary,
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    borderRadius: radius.pill,
  },
  aiTagText: { color: colors.onBrandTertiary, fontSize: 10, fontWeight: "700" },
  cardDate: { color: colors.muted, fontSize: 12, fontWeight: "600" },
  cardTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
  cardAuthor: { color: colors.muted, fontSize: 12, marginTop: 2, marginBottom: spacing.sm },
  cardSummary: { color: colors.onSurfaceTertiary, fontSize: 13, lineHeight: 19 },
  cardMeta: {
    flexDirection: "row",
    gap: spacing.sm,
    marginTop: spacing.md,
    flexWrap: "wrap",
  },
  metaBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 3,
    backgroundColor: colors.surfaceTertiary,
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    borderRadius: radius.pill,
  },
  metaBadgeText: { color: colors.muted, fontSize: 11, fontWeight: "700" },
  emailBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 3,
    backgroundColor: "#DCFCE7",
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    borderRadius: radius.pill,
  },
  emailBadgeText: { color: colors.success, fontSize: 10, fontWeight: "700" },
  fab: {
    position: "absolute",
    right: spacing.lg,
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderRadius: radius.pill,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs,
    shadowColor: "#000",
    shadowOpacity: 0.2,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 4 },
    elevation: 4,
  },
  fabText: { color: colors.onBrandPrimary, fontWeight: "700" },
});
