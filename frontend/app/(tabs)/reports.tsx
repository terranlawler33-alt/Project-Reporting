import { useCallback, useEffect, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  RefreshControl,
  ActivityIndicator,
  Share,
  Modal,
  Alert,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useRouter, useFocusEffect } from "expo-router";
import { api } from "@/src/api";
import { priorityLevelColor } from "@/src/priority";
import { colors, spacing, radius } from "@/src/theme";

export default function ReportsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [reports, setReports] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [menuFor, setMenuFor] = useState<any | null>(null);

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

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const visible = reports.filter((r) => showArchived || !r.archived);

  const doShare = async (r: any) => {
    setMenuFor(null);
    let link = "";
    try {
      const linkRes = await api.createPortalLink(r.id);
      link = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api/public/reports/${linkRes.token}`;
    } catch {}
    const body =
      `${r.project_name || r.project_code || "Daily Report"} — ${r.report_date}\n` +
      `From ${r.author_name} (${r.author_role})\n\n` +
      `${r.ai_summary}\n\n` +
      (link ? `View online: ${link}\n` : "");
    try {
      await Share.share({
        message: body,
        title: `Daily Report — ${r.report_date}`,
      });
    } catch {}
  };

  const doArchive = async (r: any) => {
    setMenuFor(null);
    try {
      if (r.archived) await api.unarchiveReport(r.id);
      else await api.archiveReport(r.id);
      await load();
    } catch {}
  };

  const doDelete = (r: any) => {
    setMenuFor(null);
    Alert.alert("Delete report?", "This will move the report to trash.", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Delete",
        style: "destructive",
        onPress: async () => {
          try {
            await api.deleteReport(r.id);
            await load();
          } catch {}
        },
      },
    ]);
  };

  const doEdit = (r: any) => {
    setMenuFor(null);
    router.push(`/report/edit/${r.id}`);
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <View style={{ flex: 1 }}>
          <Text style={styles.headerTitle}>Daily Reports</Text>
          <Text style={styles.headerSub}>AI-summarized field ops</Text>
        </View>
        <Pressable
          testID="toggle-archived"
          onPress={() => setShowArchived((s) => !s)}
          style={styles.headerToggle}
        >
          <Ionicons
            name={showArchived ? "eye-off" : "archive"}
            size={16}
            color={colors.brandPrimary}
          />
          <Text style={styles.headerToggleText}>
            {showArchived ? "Hide archived" : "Show archived"}
          </Text>
        </Pressable>
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
          {visible.length === 0 ? (
            <View style={styles.empty}>
              <Ionicons name="document-text-outline" size={40} color={colors.muted} />
              <Text style={styles.emptyText}>No reports</Text>
              <Text style={styles.emptySub}>
                Tap "Create Report" to compose your first daily summary.
              </Text>
            </View>
          ) : (
            visible.map((r) => (
              <View key={r.id} style={styles.cardWrap}>
                <Pressable
                  testID={`report-card-${r.id}`}
                  onPress={() => router.push(`/report/${r.id}`)}
                  style={({ pressed }) => [styles.card, pressed && { opacity: 0.85 }, r.archived && { opacity: 0.7 }]}
                >
                  <View style={styles.cardTop}>
                    <View style={styles.aiTag}>
                      <Ionicons name="sparkles" size={12} color={colors.onBrandTertiary} />
                      <Text style={styles.aiTagText}>AI Summary</Text>
                    </View>
                    {r.priority_level ? (
                      <View
                        testID={`report-priority-${r.id}`}
                        style={[
                          styles.priorityLevelChip,
                          { backgroundColor: priorityLevelColor(r.priority_level).bg },
                        ]}
                      >
                        <Text
                          style={[
                            styles.priorityLevelText,
                            { color: priorityLevelColor(r.priority_level).text },
                          ]}
                        >
                          {r.priority_level.toUpperCase()}
                        </Text>
                      </View>
                    ) : null}
                    <Text style={styles.cardDate}>{r.report_date}</Text>
                  </View>
                  <Text style={styles.cardTitle} numberOfLines={1}>
                    {r.project_name || r.project_code || "Daily Report"}
                    {r.archived ? "  · ARCHIVED" : ""}
                  </Text>
                  <Text style={styles.cardAuthor}>{r.author_name} · {r.author_role}</Text>
                  <Text style={styles.cardSummary} numberOfLines={3}>{r.ai_summary}</Text>
                  <View style={styles.cardMeta}>
                    <MetaBadge icon="location" count={r.visits?.length || 0} />
                    <MetaBadge icon="pause" count={r.breaks?.length || 0} />
                    <MetaBadge icon="chatbubble" count={r.sms_logs?.length || 0} />
                    {r.signature ? (
                      <View style={styles.signedBadge}>
                        <Ionicons name="checkmark-circle" size={11} color={colors.success} />
                        <Text style={styles.signedBadgeText}>Signed</Text>
                      </View>
                    ) : null}
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
                <Pressable
                  testID={`report-menu-${r.id}`}
                  onPress={() => setMenuFor(r)}
                  style={styles.kebab}
                  hitSlop={10}
                >
                  <Ionicons name="ellipsis-horizontal" size={20} color={colors.onSurface} />
                </Pressable>
              </View>
            ))
          )}
        </ScrollView>
      )}

      <Pressable
        testID="create-report-button"
        onPress={() => router.push("/report/new")}
        style={[styles.fab, { bottom: (insets.bottom || 0) + 80 }]}
      >
        <Ionicons name="add" size={22} color={colors.onBrandPrimary} />
        <Text style={styles.fabText}>Create Report</Text>
      </Pressable>

      <Modal
        visible={menuFor !== null}
        animationType="fade"
        transparent
        onRequestClose={() => setMenuFor(null)}
      >
        <Pressable style={styles.backdrop} onPress={() => setMenuFor(null)} testID="menu-backdrop" />
        <View style={[styles.sheet, { paddingBottom: (insets.bottom || 0) + spacing.lg }]}>
          <View style={styles.sheetHandle} />
          <Text style={styles.sheetTitle} numberOfLines={1}>
            {menuFor?.project_name || menuFor?.project_code || "Report"}
          </Text>
          <SheetItem
            icon="create"
            label="Edit"
            onPress={() => menuFor && doEdit(menuFor)}
            testID="menu-edit"
          />
          <SheetItem
            icon="share-social"
            label="Share (email / SMS)"
            onPress={() => menuFor && doShare(menuFor)}
            testID="menu-share"
          />
          <SheetItem
            icon={menuFor?.archived ? "arrow-undo" : "archive"}
            label={menuFor?.archived ? "Unarchive" : "Archive"}
            onPress={() => menuFor && doArchive(menuFor)}
            testID="menu-archive"
          />
          <SheetItem
            icon="trash"
            label="Delete"
            onPress={() => menuFor && doDelete(menuFor)}
            testID="menu-delete"
            danger
          />
        </View>
      </Modal>
    </View>
  );
}

function SheetItem({
  icon,
  label,
  onPress,
  testID,
  danger,
}: {
  icon: any;
  label: string;
  onPress: () => void;
  testID: string;
  danger?: boolean;
}) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      style={({ pressed }) => [styles.sheetItem, pressed && { opacity: 0.7 }]}
    >
      <View style={[styles.sheetIcon, danger && { backgroundColor: "#FEE2E2" }]}>
        <Ionicons name={icon} size={18} color={danger ? colors.error : colors.onBrandTertiary} />
      </View>
      <Text style={[styles.sheetItemText, danger && { color: colors.error }]}>{label}</Text>
    </Pressable>
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
    flexDirection: "row",
    alignItems: "flex-end",
    gap: spacing.sm,
  },
  headerTitle: { fontSize: 24, fontWeight: "700", color: colors.onSurface },
  headerSub: { color: colors.muted, fontSize: 12, marginTop: 2 },
  headerToggle: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    backgroundColor: colors.brandTertiary,
    paddingHorizontal: spacing.sm,
    paddingVertical: 6,
    borderRadius: radius.pill,
  },
  headerToggleText: { color: colors.onBrandTertiary, fontSize: 11, fontWeight: "700" },
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
  cardWrap: { position: "relative", marginBottom: spacing.md },
  card: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  kebab: {
    position: "absolute",
    top: spacing.sm,
    right: spacing.sm,
    padding: spacing.xs,
    width: 32,
    height: 32,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radius.md,
  },
  cardTop: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: spacing.sm,
    paddingRight: 32,
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
  priorityLevelChip: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    borderRadius: radius.pill,
  },
  priorityLevelText: { fontSize: 10, fontWeight: "800", letterSpacing: 0.5 },
  cardDate: { color: colors.muted, fontSize: 12, fontWeight: "600" },
  cardTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
  cardAuthor: { color: colors.muted, fontSize: 12, marginTop: 2, marginBottom: spacing.sm },
  cardSummary: { color: colors.onSurfaceTertiary, fontSize: 13, lineHeight: 19 },
  cardMeta: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md, flexWrap: "wrap" },
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
  signedBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 3,
    backgroundColor: "#DCFCE7",
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    borderRadius: radius.pill,
  },
  signedBadgeText: { color: colors.success, fontSize: 10, fontWeight: "700" },
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
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.35)" },
  sheet: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: colors.surfaceSecondary,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.xs,
  },
  sheetHandle: {
    alignSelf: "center",
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.borderStrong,
    marginBottom: spacing.md,
  },
  sheetTitle: {
    color: colors.onSurface,
    fontWeight: "700",
    fontSize: 16,
    marginBottom: spacing.sm,
  },
  sheetItem: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radius.md,
  },
  sheetIcon: {
    width: 36,
    height: 36,
    borderRadius: radius.md,
    backgroundColor: colors.brandTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
  sheetItemText: { color: colors.onSurface, fontWeight: "600", fontSize: 15 },
});
