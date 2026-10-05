import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Modal,
  View,
  Text,
  Pressable,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  Platform,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import {
  DeviceSms,
  fetchRecentSms,
  isSmsAvailable,
  openAppSettings,
  requestSmsPermission,
} from "@/src/sms";
import { colors, spacing, radius } from "@/src/theme";

type ImportMode = "sms-log" | "visit-notes";

type Props = {
  visible: boolean;
  onClose: () => void;
  mode: ImportMode;
  /** For visit-notes mode: receives selected messages as a formatted text block. */
  onImportText?: (text: string) => void;
  /** For sms-log mode: receives raw selected items so caller can bulk-create logs. */
  onImportItems?: (items: DeviceSms[]) => void;
};

type Phase = "idle" | "requesting" | "loading" | "ready" | "denied" | "blocked" | "unsupported" | "error";

const formatTime = (epoch: number) => {
  try {
    const d = new Date(epoch);
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    if (isToday) return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    return d.toLocaleDateString([], { month: "short", day: "numeric" }) +
      " · " +
      d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  } catch {
    return "";
  }
};

export function SmsImportSheet({ visible, onClose, mode, onImportText, onImportItems }: Props) {
  const insets = useSafeAreaInsets();
  const [phase, setPhase] = useState<Phase>("idle");
  const [messages, setMessages] = useState<DeviceSms[]>([]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});

  const refresh = useCallback(async () => {
    if (!isSmsAvailable()) {
      setPhase("unsupported");
      return;
    }
    setPhase("requesting");
    const perm = await requestSmsPermission();
    if (!perm.granted) {
      setPhase(perm.canAskAgain ? "denied" : "blocked");
      return;
    }
    setPhase("loading");
    try {
      const msgs = await fetchRecentSms(7, 300);
      setMessages(msgs);
      setPhase("ready");
    } catch {
      setPhase("error");
    }
  }, []);

  useEffect(() => {
    if (!visible) return;
    setSelected({});
    if (!isSmsAvailable()) {
      setPhase("unsupported");
    } else {
      refresh();
    }
  }, [visible, refresh]);

  const toggle = (id: string) =>
    setSelected((s) => ({ ...s, [id]: !s[id] }));

  const selectedItems = useMemo(
    () => messages.filter((m) => selected[m.id]),
    [messages, selected],
  );

  const selectAll = () => {
    const all: Record<string, boolean> = {};
    for (const m of messages) all[m.id] = true;
    setSelected(all);
  };

  const clearAll = () => setSelected({});

  const importSelected = () => {
    if (selectedItems.length === 0) return;
    if (mode === "visit-notes" && onImportText) {
      const text = selectedItems
        .map((m) => {
          const who = m.display_name || m.address || "Unknown";
          const when = formatTime(m.date);
          return `[SMS ${when}] ${who}: ${m.body}`;
        })
        .join("\n");
      onImportText(text);
    } else if (mode === "sms-log" && onImportItems) {
      onImportItems(selectedItems);
    }
    onClose();
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <View style={[styles.sheet, { paddingBottom: (insets.bottom || 0) + spacing.lg }]}>
          <View style={styles.handle} />
          <View style={styles.header}>
            <View style={{ flex: 1 }}>
              <Text style={styles.title}>Import from phone</Text>
              <Text style={styles.subtitle}>
                {phase === "ready"
                  ? `${messages.length} message${messages.length === 1 ? "" : "s"} · last 7 days`
                  : "Pick texts to add to your report"}
              </Text>
            </View>
            <Pressable onPress={onClose} testID="sms-import-close" hitSlop={10}>
              <Ionicons name="close" size={24} color={colors.onSurface} />
            </Pressable>
          </View>

          <View style={styles.body}>
            {phase === "unsupported" && (
              <IosRestrictionBlock />
            )}
            {(phase === "idle" || phase === "requesting" || phase === "loading") && (
              <View style={styles.center}>
                <ActivityIndicator color={colors.brandPrimary} />
                <Text style={styles.hintText}>
                  {phase === "requesting" ? "Waiting for permission…" : "Loading messages…"}
                </Text>
              </View>
            )}
            {(phase === "denied" || phase === "blocked") && (
              <PermissionBlock
                blocked={phase === "blocked"}
                onRetry={refresh}
                onSettings={openAppSettings}
              />
            )}
            {phase === "error" && (
              <View style={styles.center}>
                <Ionicons name="warning" size={28} color={colors.error} />
                <Text style={styles.hintText}>Couldn't read messages.</Text>
                <Pressable onPress={refresh} style={styles.secondaryBtn} testID="sms-import-retry">
                  <Text style={styles.secondaryBtnText}>Retry</Text>
                </Pressable>
              </View>
            )}
            {phase === "ready" && (
              <>
                {messages.length === 0 ? (
                  <View style={styles.center}>
                    <Ionicons name="chatbubbles-outline" size={32} color={colors.muted} />
                    <Text style={styles.hintText}>No texts in the last 7 days.</Text>
                  </View>
                ) : (
                  <>
                    <View style={styles.actionsRow}>
                      <Pressable onPress={selectAll} testID="sms-import-select-all">
                        <Text style={styles.linkText}>Select all</Text>
                      </Pressable>
                      <Pressable onPress={clearAll} testID="sms-import-clear" disabled={selectedItems.length === 0}>
                        <Text
                          style={[
                            styles.linkText,
                            selectedItems.length === 0 && { color: colors.muted },
                          ]}
                        >
                          Clear
                        </Text>
                      </Pressable>
                    </View>
                    <ScrollView style={styles.list} keyboardShouldPersistTaps="handled">
                      {messages.map((m) => (
                        <Pressable
                          key={m.id}
                          onPress={() => toggle(m.id)}
                          testID={`sms-item-${m.id}`}
                          style={({ pressed }) => [
                            styles.msg,
                            selected[m.id] && styles.msgSelected,
                            pressed && { opacity: 0.9 },
                          ]}
                        >
                          <View
                            style={[
                              styles.check,
                              selected[m.id] && styles.checkOn,
                            ]}
                          >
                            {selected[m.id] ? (
                              <Ionicons name="checkmark" size={14} color={colors.onBrandPrimary} />
                            ) : null}
                          </View>
                          <View style={{ flex: 1 }}>
                            <View style={styles.msgTop}>
                              <Text style={styles.msgFrom} numberOfLines={1}>
                                {m.display_name || m.address || "Unknown"}
                              </Text>
                              <Text style={styles.msgTime}>{formatTime(m.date)}</Text>
                            </View>
                            <Text style={styles.msgBody} numberOfLines={3}>
                              {m.body}
                            </Text>
                          </View>
                        </Pressable>
                      ))}
                    </ScrollView>
                  </>
                )}
              </>
            )}
          </View>

          <Pressable
            onPress={importSelected}
            disabled={selectedItems.length === 0 || phase !== "ready"}
            testID="sms-import-confirm"
            style={({ pressed }) => [
              styles.primaryBtn,
              pressed && { opacity: 0.85 },
              (selectedItems.length === 0 || phase !== "ready") && { opacity: 0.5 },
            ]}
          >
            <Ionicons name="download" size={18} color={colors.onBrandPrimary} />
            <Text style={styles.primaryBtnText}>
              Import {selectedItems.length > 0 ? `(${selectedItems.length})` : ""}
            </Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

function IosRestrictionBlock() {
  return (
    <View style={styles.center}>
      <View style={styles.iosIcon}>
        <Ionicons name="phone-portrait" size={28} color={colors.muted} />
      </View>
      <Text style={styles.iosTitle}>Not supported on iOS</Text>
      <Text style={styles.hintText}>
        Apple restricts apps from reading your SMS inbox. On iPhone, add messages manually using the
        "Log Communication" form below.
      </Text>
    </View>
  );
}

function PermissionBlock({
  blocked,
  onRetry,
  onSettings,
}: {
  blocked: boolean;
  onRetry: () => void;
  onSettings: () => void;
}) {
  return (
    <View style={styles.center}>
      <View style={styles.iosIcon}>
        <Ionicons name="lock-closed" size={26} color={colors.muted} />
      </View>
      <Text style={styles.iosTitle}>
        {blocked ? "SMS access blocked" : "SMS permission needed"}
      </Text>
      <Text style={styles.hintText}>
        {blocked
          ? "You've turned off SMS access for Summar-Eeze. Open settings to enable it."
          : "Allow SMS access to pull recent texts into this report."}
      </Text>
      {blocked ? (
        <Pressable onPress={onSettings} style={styles.secondaryBtn} testID="sms-import-settings">
          <Ionicons name="settings" size={14} color={colors.brandPrimary} />
          <Text style={styles.secondaryBtnText}>Open Settings</Text>
        </Pressable>
      ) : (
        <Pressable onPress={onRetry} style={styles.secondaryBtn} testID="sms-import-grant">
          <Text style={styles.secondaryBtnText}>Grant access</Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.4)",
    justifyContent: "flex-end",
  },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    maxHeight: "85%",
    paddingTop: spacing.sm,
  },
  handle: {
    alignSelf: "center",
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.borderStrong,
    marginBottom: spacing.sm,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  title: { color: colors.onSurface, fontWeight: "700", fontSize: 17 },
  subtitle: { color: colors.muted, fontSize: 12, marginTop: 2 },
  body: { flexShrink: 1, paddingHorizontal: spacing.lg, paddingTop: spacing.sm, minHeight: 220 },
  center: {
    paddingVertical: spacing.xl,
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
  },
  iosIcon: {
    width: 56,
    height: 56,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
  iosTitle: { color: colors.onSurface, fontWeight: "700", fontSize: 15 },
  hintText: {
    color: colors.muted,
    fontSize: 12,
    textAlign: "center",
    paddingHorizontal: spacing.lg,
    lineHeight: 17,
  },
  actionsRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingBottom: spacing.xs,
  },
  linkText: { color: colors.brandPrimary, fontWeight: "700", fontSize: 12 },
  list: { maxHeight: 420 },
  msg: {
    flexDirection: "row",
    gap: spacing.sm,
    padding: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.xs,
    alignItems: "flex-start",
  },
  msgSelected: {
    borderColor: colors.brandPrimary,
    backgroundColor: colors.brandTertiary,
  },
  check: {
    width: 22,
    height: 22,
    borderRadius: radius.pill,
    borderWidth: 1.5,
    borderColor: colors.borderStrong,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 1,
  },
  checkOn: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  msgTop: {
    flexDirection: "row",
    justifyContent: "space-between",
    gap: spacing.sm,
  },
  msgFrom: { color: colors.onSurface, fontWeight: "700", fontSize: 13, flex: 1 },
  msgTime: { color: colors.muted, fontSize: 11 },
  msgBody: { color: colors.onSurfaceTertiary, fontSize: 13, marginTop: 2 },
  primaryBtn: {
    marginHorizontal: spacing.lg,
    marginTop: spacing.md,
    backgroundColor: colors.brandPrimary,
    padding: spacing.md + 2,
    borderRadius: radius.md,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: spacing.xs,
  },
  primaryBtnText: { color: colors.onBrandPrimary, fontWeight: "700", fontSize: 15 },
  secondaryBtn: {
    marginTop: spacing.sm,
    paddingVertical: 8,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.brandPrimary,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  secondaryBtnText: { color: colors.brandPrimary, fontWeight: "700", fontSize: 12 },
});
