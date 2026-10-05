import { useCallback, useEffect, useMemo, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  Pressable,
  ActivityIndicator,
  Modal,
  Alert,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useRouter, useFocusEffect } from "expo-router";
import { api } from "@/src/api";
import { colors, spacing, radius } from "@/src/theme";

type Resp = {
  id: string;
  report_id: string;
  project_id?: string | null;
  project_label?: string | null;
  project_flag?: string | null;
  reporter_name?: string | null;
  reporter_email?: string | null;
  message: string;
  created_at: string;
  read_at?: string | null;
  archived?: boolean;
};

const formatWhen = (iso: string) => {
  try {
    const d = new Date(iso);
    const now = new Date();
    const today = d.toDateString() === now.toDateString();
    if (today) return `Today · ${d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
    return (
      d.toLocaleDateString([], { month: "short", day: "numeric" }) +
      " · " +
      d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
    );
  } catch {
    return iso;
  }
};

export default function MailScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [items, setItems] = useState<Resp[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [filter, setFilter] = useState<"all" | "unread">("all");
  const [open, setOpen] = useState<Resp | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await api.listResponses({ include_archived: showArchived });
      setItems(r || []);
    } catch {}
    setLoading(false);
  }, [showArchived]);

  useEffect(() => {
    load();
  }, [load]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const visible = useMemo(() => {
    if (filter === "unread") return items.filter((i) => !i.read_at);
    return items;
  }, [items, filter]);

  const unreadCount = useMemo(() => items.filter((i) => !i.read_at).length, [items]);

  const openResponse = async (r: Resp) => {
    setOpen(r);
    if (!r.read_at) {
      try {
        await api.markResponseRead(r.id);
        setItems((prev) => prev.map((x) => (x.id === r.id ? { ...x, read_at: new Date().toISOString() } : x)));
      } catch {}
    }
  };

  const toggleRead = async (r: Resp) => {
    try {
      if (r.read_at) {
        await api.markResponseUnread(r.id);
        setItems((prev) => prev.map((x) => (x.id === r.id ? { ...x, read_at: null } : x)));
      } else {
        await api.markResponseRead(r.id);
        setItems((prev) => prev.map((x) => (x.id === r.id ? { ...x, read_at: new Date().toISOString() } : x)));
      }
    } catch {}
  };

  const archive = async (r: Resp) => {
    try {
      await api.archiveResponse(r.id);
      setOpen(null);
      await load();
    } catch {}
  };

  const removeOne = (r: Resp) => {
    Alert.alert("Delete reply?", "This can't be undone.", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Delete",
        style: "destructive",
        onPress: async () => {
          try {
            await api.deleteResponse(r.id);
            setOpen(null);
            await load();
          } catch {}
        },
      },
    ]);
  };

  const openJob = (r: Resp) => {
    setOpen(null);
    router.push(`/report/${r.report_id}`);
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <View style={{ flex: 1 }}>
          <Text style={styles.headerTitle}>Mail</Text>
          <Text style={styles.headerSub}>
            {unreadCount > 0 ? `${unreadCount} unread reply${unreadCount === 1 ? "" : "ies"}` : "All caught up"}
          </Text>
        </View>
        <Pressable
          testID="mail-toggle-archived"
          onPress={() => setShowArchived((s) => !s)}
          style={styles.headerToggle}
        >
          <Ionicons name={showArchived ? "eye-off" : "archive"} size={14} color={colors.brandPrimary} />
          <Text style={styles.headerToggleText}>{showArchived ? "Hide archived" : "Show archived"}</Text>
        </Pressable>
      </View>

      <View style={styles.filterBar}>
        <Pressable
          testID="mail-filter-all"
          onPress={() => setFilter("all")}
          style={[styles.filterChip, filter === "all" && styles.filterChipActive]}
        >
          <Text style={[styles.filterText, filter === "all" && styles.filterTextActive]}>All</Text>
        </Pressable>
        <Pressable
          testID="mail-filter-unread"
          onPress={() => setFilter("unread")}
          style={[styles.filterChip, filter === "unread" && styles.filterChipActive]}
        >
          <Text style={[styles.filterText, filter === "unread" && styles.filterTextActive]}>
            Unread{unreadCount > 0 ? ` · ${unreadCount}` : ""}
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
              <Ionicons name="mail-open-outline" size={44} color={colors.muted} />
              <Text style={styles.emptyText}>No replies yet</Text>
              <Text style={styles.emptySub}>
                When someone replies to a flagged job via your shared report link, it'll land here.
              </Text>
            </View>
          ) : (
            visible.map((r) => (
              <Pressable
                key={r.id}
                testID={`mail-item-${r.id}`}
                onPress={() => openResponse(r)}
                style={({ pressed }) => [styles.item, pressed && { opacity: 0.85 }]}
              >
                <View style={styles.itemLeft}>
                  <View style={[styles.avatar, !r.read_at && styles.avatarUnread]}>
                    <Text style={styles.avatarText}>
                      {(r.reporter_name || r.reporter_email || "?").slice(0, 1).toUpperCase()}
                    </Text>
                  </View>
                  {!r.read_at ? <View style={styles.unreadDot} /> : null}
                </View>
                <View style={{ flex: 1 }}>
                  <View style={styles.itemTop}>
                    <Text
                      style={[styles.itemFrom, !r.read_at && styles.itemFromUnread]}
                      numberOfLines={1}
                    >
                      {r.reporter_name || r.reporter_email || "Anonymous reply"}
                    </Text>
                    <Text style={styles.itemWhen}>{formatWhen(r.created_at)}</Text>
                  </View>
                  <View style={styles.itemJob}>
                    {r.project_flag ? (
                      <View style={styles.flagChip}>
                        <Ionicons name="flag" size={10} color={colors.error} />
                        <Text style={styles.flagChipText}>{r.project_flag}</Text>
                      </View>
                    ) : null}
                    <Text style={styles.itemJobText} numberOfLines={1}>
                      {r.project_label || "General reply"}
                    </Text>
                  </View>
                  <Text style={styles.itemPreview} numberOfLines={2}>
                    {r.message}
                  </Text>
                </View>
              </Pressable>
            ))
          )}
        </ScrollView>
      )}

      {/* Detail modal */}
      <Modal
        visible={open !== null}
        transparent
        animationType="slide"
        onRequestClose={() => setOpen(null)}
      >
        <Pressable style={styles.backdrop} onPress={() => setOpen(null)} testID="mail-detail-backdrop" />
        <View style={[styles.sheet, { paddingBottom: (insets.bottom || 0) + spacing.lg }]}>
          {open ? (
            <>
              <View style={styles.sheetHandle} />
              <View style={styles.sheetHeader}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.sheetTitle} numberOfLines={1}>
                    {open.reporter_name || open.reporter_email || "Anonymous reply"}
                  </Text>
                  {open.reporter_email ? (
                    <Text style={styles.sheetSub}>{open.reporter_email}</Text>
                  ) : null}
                </View>
                <Pressable onPress={() => setOpen(null)} testID="mail-detail-close" hitSlop={10}>
                  <Ionicons name="close" size={24} color={colors.onSurface} />
                </Pressable>
              </View>

              <View style={styles.jobCard}>
                <View style={styles.jobCardRow}>
                  <Text style={styles.jobCardLabel}>Replying to</Text>
                  {open.project_flag ? (
                    <View style={styles.flagChip}>
                      <Ionicons name="flag" size={10} color={colors.error} />
                      <Text style={styles.flagChipText}>{open.project_flag}</Text>
                    </View>
                  ) : null}
                </View>
                <Text style={styles.jobCardTitle}>{open.project_label || "General reply"}</Text>
                <Pressable onPress={() => openJob(open)} testID="mail-open-job" style={styles.linkRow}>
                  <Ionicons name="document-text" size={14} color={colors.brandPrimary} />
                  <Text style={styles.linkRowText}>Open full report</Text>
                </Pressable>
              </View>

              <ScrollView style={styles.messageBox}>
                <Text style={styles.messageText}>{open.message}</Text>
              </ScrollView>

              <Text style={styles.sheetWhen}>
                Received {formatWhen(open.created_at)}
              </Text>

              <View style={styles.actionRow}>
                <Pressable
                  testID="mail-toggle-read"
                  onPress={() => open && toggleRead(open)}
                  style={styles.secondaryBtn}
                >
                  <Ionicons name={open.read_at ? "mail" : "mail-open"} size={14} color={colors.brandPrimary} />
                  <Text style={styles.secondaryBtnText}>
                    Mark {open.read_at ? "unread" : "read"}
                  </Text>
                </Pressable>
                <Pressable
                  testID="mail-archive"
                  onPress={() => open && archive(open)}
                  style={styles.secondaryBtn}
                >
                  <Ionicons name="archive" size={14} color={colors.brandPrimary} />
                  <Text style={styles.secondaryBtnText}>Archive</Text>
                </Pressable>
                <Pressable
                  testID="mail-delete"
                  onPress={() => open && removeOne(open)}
                  style={[styles.secondaryBtn, styles.dangerBtn]}
                >
                  <Ionicons name="trash" size={14} color={colors.error} />
                  <Text style={[styles.secondaryBtnText, { color: colors.error }]}>Delete</Text>
                </Pressable>
              </View>
            </>
          ) : null}
        </View>
      </Modal>
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
  filterBar: {
    flexDirection: "row",
    gap: spacing.xs,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    backgroundColor: colors.surfaceSecondary,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  filterChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceTertiary,
  },
  filterChipActive: { borderColor: colors.brandPrimary, backgroundColor: colors.brandPrimary },
  filterText: { fontSize: 12, fontWeight: "700", color: colors.onSurface },
  filterTextActive: { color: colors.onBrandPrimary },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  empty: {
    padding: spacing.xxl,
    alignItems: "center",
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  emptyText: { fontWeight: "700", color: colors.onSurface, marginTop: spacing.sm, fontSize: 14 },
  emptySub: {
    color: colors.muted,
    fontSize: 12,
    marginTop: spacing.xs,
    textAlign: "center",
    lineHeight: 17,
  },
  item: {
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
  itemLeft: { position: "relative" },
  avatar: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarUnread: { backgroundColor: colors.brandPrimary },
  avatarText: { color: colors.onBrandPrimary, fontWeight: "800", fontSize: 15 },
  unreadDot: {
    position: "absolute",
    top: -2,
    right: -2,
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: colors.error,
    borderWidth: 2,
    borderColor: colors.surfaceSecondary,
  },
  itemTop: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: spacing.sm,
  },
  itemFrom: { color: colors.onSurface, fontWeight: "600", fontSize: 14, flex: 1 },
  itemFromUnread: { fontWeight: "800" },
  itemWhen: { color: colors.muted, fontSize: 11 },
  itemJob: {
    flexDirection: "row",
    gap: 6,
    alignItems: "center",
    marginTop: 4,
  },
  itemJobText: { color: colors.muted, fontSize: 12, flex: 1 },
  flagChip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 3,
    backgroundColor: "#FEE2E2",
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: radius.pill,
  },
  flagChipText: { color: colors.error, fontSize: 10, fontWeight: "700" },
  itemPreview: { color: colors.onSurfaceTertiary, fontSize: 13, marginTop: 6, lineHeight: 18 },
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)" },
  sheet: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    padding: spacing.lg,
    maxHeight: "85%",
  },
  sheetHandle: {
    alignSelf: "center",
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.borderStrong,
    marginBottom: spacing.md,
  },
  sheetHeader: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: spacing.md,
  },
  sheetTitle: { color: colors.onSurface, fontWeight: "800", fontSize: 18 },
  sheetSub: { color: colors.muted, fontSize: 12, marginTop: 2 },
  jobCard: {
    padding: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.md,
  },
  jobCardRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  jobCardLabel: { color: colors.muted, fontSize: 11, textTransform: "uppercase", fontWeight: "700" },
  jobCardTitle: { color: colors.onSurface, fontWeight: "700", fontSize: 15, marginTop: 4 },
  linkRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: spacing.sm },
  linkRowText: { color: colors.brandPrimary, fontWeight: "700", fontSize: 12 },
  messageBox: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    maxHeight: 260,
  },
  messageText: { color: colors.onSurface, fontSize: 14, lineHeight: 21 },
  sheetWhen: { color: colors.muted, fontSize: 11, marginTop: spacing.sm, marginBottom: spacing.md },
  actionRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  secondaryBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.brandPrimary,
  },
  secondaryBtnText: { color: colors.brandPrimary, fontWeight: "700", fontSize: 12 },
  dangerBtn: { borderColor: colors.error },
});
