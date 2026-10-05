import { useEffect, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ScrollView,
  TextInput,
  Modal,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Switch,
  Alert,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { colors, spacing, radius } from "@/src/theme";
import { PriorityFlagDef } from "@/src/priority";

type EditorMode = "add" | "edit";

export default function CustomListsSettings() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [breakTypes, setBreakTypes] = useState<string[]>([]);
  const [flags, setFlags] = useState<PriorityFlagDef[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  // Editor modal state
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorKind, setEditorKind] = useState<"break" | "flag">("break");
  const [editorMode, setEditorMode] = useState<EditorMode>("add");
  const [editorIndex, setEditorIndex] = useState<number | null>(null);
  const [editorLabel, setEditorLabel] = useState("");
  const [editorRequiresReason, setEditorRequiresReason] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.getUserLists();
        setBreakTypes(res.break_types || []);
        setFlags(
          (res.priority_flags || []).map((f: any) => ({
            type: f.type,
            requiresReason: !!f.requires_reason,
          })),
        );
      } catch (e: any) {
        Alert.alert("Failed to load", e?.message || "Please retry.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const openAdd = (kind: "break" | "flag") => {
    setEditorKind(kind);
    setEditorMode("add");
    setEditorIndex(null);
    setEditorLabel("");
    setEditorRequiresReason(false);
    setEditorOpen(true);
  };

  const openEdit = (kind: "break" | "flag", index: number) => {
    setEditorKind(kind);
    setEditorMode("edit");
    setEditorIndex(index);
    if (kind === "break") {
      setEditorLabel(breakTypes[index] || "");
      setEditorRequiresReason(false);
    } else {
      const f = flags[index];
      setEditorLabel(f?.type || "");
      setEditorRequiresReason(!!f?.requiresReason);
    }
    setEditorOpen(true);
  };

  const applyEditor = () => {
    const label = editorLabel.trim();
    if (!label) {
      Alert.alert("Empty label", "Give it a short label first.");
      return;
    }
    if (editorKind === "break") {
      const next = [...breakTypes];
      if (editorMode === "add") next.push(label);
      else if (editorIndex != null) next[editorIndex] = label;
      // Dedupe (case-insensitive) — keep first occurrence
      const seen = new Set<string>();
      const clean = next.filter((s) => {
        const k = s.toLowerCase();
        if (seen.has(k)) return false;
        seen.add(k);
        return true;
      });
      setBreakTypes(clean);
    } else {
      const next = [...flags];
      const entry = { type: label, requiresReason: editorRequiresReason };
      if (editorMode === "add") next.push(entry);
      else if (editorIndex != null) next[editorIndex] = entry;
      const seen = new Set<string>();
      const clean = next.filter((f) => {
        const k = f.type.toLowerCase();
        if (seen.has(k)) return false;
        seen.add(k);
        return true;
      });
      setFlags(clean);
    }
    setDirty(true);
    setEditorOpen(false);
  };

  const removeItem = (kind: "break" | "flag", index: number) => {
    Alert.alert(
      "Remove item?",
      kind === "break"
        ? `Remove "${breakTypes[index]}" from your break types?`
        : `Remove "${flags[index].type}" from your priority flags?`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Remove",
          style: "destructive",
          onPress: () => {
            if (kind === "break") {
              setBreakTypes(breakTypes.filter((_, i) => i !== index));
            } else {
              setFlags(flags.filter((_, i) => i !== index));
            }
            setDirty(true);
          },
        },
      ],
    );
  };

  const move = (kind: "break" | "flag", index: number, dir: -1 | 1) => {
    const target = index + dir;
    if (kind === "break") {
      if (target < 0 || target >= breakTypes.length) return;
      const next = [...breakTypes];
      [next[index], next[target]] = [next[target], next[index]];
      setBreakTypes(next);
    } else {
      if (target < 0 || target >= flags.length) return;
      const next = [...flags];
      [next[index], next[target]] = [next[target], next[index]];
      setFlags(next);
    }
    setDirty(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.putUserLists({
        break_types: breakTypes,
        priority_flags: flags.map((f) => ({
          type: f.type,
          requires_reason: !!f.requiresReason,
        })),
      });
      setDirty(false);
      Alert.alert("Saved", "Your custom lists have been saved.");
    } catch (e: any) {
      Alert.alert("Save failed", e?.message || "Please retry.");
    } finally {
      setSaving(false);
    }
  };

  const resetDefaults = () => {
    Alert.alert(
      "Reset to defaults?",
      "This restores the built-in break types and priority flags. Custom entries will be lost.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Reset",
          style: "destructive",
          onPress: async () => {
            setSaving(true);
            try {
              const res = await api.resetUserLists();
              setBreakTypes(res.break_types || []);
              setFlags(
                (res.priority_flags || []).map((f: any) => ({
                  type: f.type,
                  requiresReason: !!f.requires_reason,
                })),
              );
              setDirty(false);
            } finally {
              setSaving(false);
            }
          },
        },
      ],
    );
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.surface }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} testID="settings-back">
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <View style={{ flex: 1, marginLeft: spacing.sm }}>
          <Text style={styles.headerTitle}>Custom Lists</Text>
          <Text style={styles.headerSub}>
            Add, edit or delete break types and priority flags
          </Text>
        </View>
        {dirty && !saving ? (
          <Pressable testID="settings-save" onPress={save} style={styles.saveBtn}>
            <Text style={styles.saveBtnText}>Save</Text>
          </Pressable>
        ) : saving ? (
          <ActivityIndicator color={colors.brandPrimary} />
        ) : null}
      </View>

      {loading ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xxl }} />
      ) : (
        <ScrollView
          contentContainerStyle={{
            padding: spacing.lg,
            paddingBottom: (insets.bottom || 0) + spacing.xxl,
          }}
        >
          {/* Break Types */}
          <View style={styles.sectionHeader}>
            <Ionicons name="cafe" size={16} color={colors.brandPrimary} />
            <Text style={styles.sectionTitle}>Break Types</Text>
            <Text style={styles.sectionCount}>{breakTypes.length}</Text>
          </View>
          <Text style={styles.hint}>Shown when you start a break.</Text>
          {breakTypes.length === 0 ? (
            <Text style={styles.emptyText}>No break types yet. Add one below.</Text>
          ) : (
            breakTypes.map((b, i) => (
              <View key={`b-${b}-${i}`} style={styles.row} testID={`break-row-${i}`}>
                <Text style={styles.rowLabel} numberOfLines={1}>{b}</Text>
                <Pressable
                  testID={`break-up-${i}`}
                  onPress={() => move("break", i, -1)}
                  disabled={i === 0}
                  hitSlop={6}
                  style={[styles.iconBtn, i === 0 && { opacity: 0.3 }]}
                >
                  <Ionicons name="arrow-up" size={16} color={colors.onSurface} />
                </Pressable>
                <Pressable
                  testID={`break-down-${i}`}
                  onPress={() => move("break", i, 1)}
                  disabled={i === breakTypes.length - 1}
                  hitSlop={6}
                  style={[styles.iconBtn, i === breakTypes.length - 1 && { opacity: 0.3 }]}
                >
                  <Ionicons name="arrow-down" size={16} color={colors.onSurface} />
                </Pressable>
                <Pressable
                  testID={`break-edit-${i}`}
                  onPress={() => openEdit("break", i)}
                  hitSlop={6}
                  style={styles.iconBtn}
                >
                  <Ionicons name="create-outline" size={18} color={colors.brandPrimary} />
                </Pressable>
                <Pressable
                  testID={`break-delete-${i}`}
                  onPress={() => removeItem("break", i)}
                  hitSlop={6}
                  style={styles.iconBtn}
                >
                  <Ionicons name="trash-outline" size={18} color={colors.error} />
                </Pressable>
              </View>
            ))
          )}
          <Pressable
            testID="break-add"
            onPress={() => openAdd("break")}
            style={styles.addBtn}
          >
            <Ionicons name="add-circle" size={18} color={colors.onBrandPrimary} />
            <Text style={styles.addBtnText}>Add break type</Text>
          </Pressable>

          {/* Priority Flags */}
          <View style={[styles.sectionHeader, { marginTop: spacing.xl }]}>
            <Ionicons name="flag" size={16} color={colors.brandPrimary} />
            <Text style={styles.sectionTitle}>Priority Flags</Text>
            <Text style={styles.sectionCount}>{flags.length}</Text>
          </View>
          <Text style={styles.hint}>
            Shown when you set the priority level on a report. Toggle &quot;Requires reason&quot; to force a
            short explanation for that flag.
          </Text>
          {flags.length === 0 ? (
            <Text style={styles.emptyText}>No flags yet. Add one below.</Text>
          ) : (
            flags.map((f, i) => (
              <View key={`f-${f.type}-${i}`} style={styles.row} testID={`flag-row-${i}`}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowLabel} numberOfLines={1}>{f.type}</Text>
                  {f.requiresReason ? (
                    <Text style={styles.rowSub}>Requires reason *</Text>
                  ) : null}
                </View>
                <Pressable
                  testID={`flag-up-${i}`}
                  onPress={() => move("flag", i, -1)}
                  disabled={i === 0}
                  hitSlop={6}
                  style={[styles.iconBtn, i === 0 && { opacity: 0.3 }]}
                >
                  <Ionicons name="arrow-up" size={16} color={colors.onSurface} />
                </Pressable>
                <Pressable
                  testID={`flag-down-${i}`}
                  onPress={() => move("flag", i, 1)}
                  disabled={i === flags.length - 1}
                  hitSlop={6}
                  style={[styles.iconBtn, i === flags.length - 1 && { opacity: 0.3 }]}
                >
                  <Ionicons name="arrow-down" size={16} color={colors.onSurface} />
                </Pressable>
                <Pressable
                  testID={`flag-edit-${i}`}
                  onPress={() => openEdit("flag", i)}
                  hitSlop={6}
                  style={styles.iconBtn}
                >
                  <Ionicons name="create-outline" size={18} color={colors.brandPrimary} />
                </Pressable>
                <Pressable
                  testID={`flag-delete-${i}`}
                  onPress={() => removeItem("flag", i)}
                  hitSlop={6}
                  style={styles.iconBtn}
                >
                  <Ionicons name="trash-outline" size={18} color={colors.error} />
                </Pressable>
              </View>
            ))
          )}
          <Pressable
            testID="flag-add"
            onPress={() => openAdd("flag")}
            style={styles.addBtn}
          >
            <Ionicons name="add-circle" size={18} color={colors.onBrandPrimary} />
            <Text style={styles.addBtnText}>Add priority flag</Text>
          </Pressable>

          <Pressable testID="settings-reset" onPress={resetDefaults} style={styles.resetBtn}>
            <Text style={styles.resetBtnText}>Reset to defaults</Text>
          </Pressable>
        </ScrollView>
      )}

      {/* Editor modal */}
      <Modal
        visible={editorOpen}
        transparent
        animationType="slide"
        onRequestClose={() => setEditorOpen(false)}
      >
        <View style={styles.modalBackdrop}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>
                {editorMode === "add" ? "Add " : "Edit "}
                {editorKind === "break" ? "break type" : "priority flag"}
              </Text>
              <Pressable onPress={() => setEditorOpen(false)} testID="settings-editor-close">
                <Ionicons name="close" size={22} color={colors.onSurface} />
              </Pressable>
            </View>
            <Text style={styles.label}>Label</Text>
            <TextInput
              testID="settings-editor-label"
              value={editorLabel}
              onChangeText={setEditorLabel}
              autoFocus
              placeholder={editorKind === "break" ? "e.g. Coffee run" : "e.g. Client Walk-through"}
              placeholderTextColor={colors.muted}
              style={styles.input}
              maxLength={editorKind === "break" ? 40 : 60}
            />
            {editorKind === "flag" ? (
              <View style={styles.switchRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.switchLabel}>Requires reason</Text>
                  <Text style={styles.switchHint}>
                    Force a short explanation when this flag is picked
                  </Text>
                </View>
                <Switch
                  testID="settings-editor-requires-reason"
                  value={editorRequiresReason}
                  onValueChange={setEditorRequiresReason}
                  trackColor={{ true: colors.brandPrimary, false: colors.borderStrong }}
                />
              </View>
            ) : null}
            <Pressable
              testID="settings-editor-apply"
              onPress={applyEditor}
              style={styles.primaryBtn}
            >
              <Text style={styles.primaryBtnText}>
                {editorMode === "add" ? "Add" : "Update"}
              </Text>
            </Pressable>
          </View>
        </View>
      </Modal>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: "row",
    alignItems: "flex-end",
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
    gap: spacing.sm,
  },
  headerTitle: { fontSize: 20, fontWeight: "800", color: colors.onSurface },
  headerSub: { color: colors.muted, fontSize: 12, marginTop: 2 },
  saveBtn: {
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.md,
  },
  saveBtnText: { color: colors.onBrandPrimary, fontWeight: "800", fontSize: 13 },
  sectionHeader: { flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 4 },
  sectionTitle: { color: colors.onSurface, fontSize: 15, fontWeight: "800", flex: 1 },
  sectionCount: {
    backgroundColor: colors.brandTertiary,
    color: colors.onBrandTertiary,
    fontSize: 11,
    fontWeight: "800",
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: radius.pill,
    overflow: "hidden",
  },
  hint: { color: colors.muted, fontSize: 11, marginBottom: spacing.sm, lineHeight: 16 },
  emptyText: {
    color: colors.muted,
    fontSize: 12,
    fontStyle: "italic",
    padding: spacing.md,
    textAlign: "center",
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    marginBottom: spacing.xs,
  },
  rowLabel: { flex: 1, color: colors.onSurface, fontSize: 14, fontWeight: "600" },
  rowSub: { color: colors.error, fontSize: 10, fontWeight: "700", marginTop: 2 },
  iconBtn: {
    width: 30,
    height: 30,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radius.sm,
  },
  addBtn: {
    marginTop: spacing.sm,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    backgroundColor: colors.brandPrimary,
    padding: spacing.md,
    borderRadius: radius.md,
  },
  addBtnText: { color: colors.onBrandPrimary, fontWeight: "800", fontSize: 14 },
  resetBtn: {
    marginTop: spacing.xxl,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.error,
    alignItems: "center",
  },
  resetBtnText: { color: colors.error, fontWeight: "800", fontSize: 13 },
  modalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.5)",
    justifyContent: "flex-end",
  },
  modalSheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: spacing.lg,
    paddingBottom: spacing.xxl,
  },
  modalHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: spacing.md,
  },
  modalTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface, flex: 1 },
  label: {
    color: colors.onSurfaceTertiary,
    fontSize: 12,
    fontWeight: "700",
    marginTop: spacing.sm,
    marginBottom: 4,
  },
  input: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    padding: spacing.md - 2,
    color: colors.onSurface,
    borderWidth: 1,
    borderColor: colors.border,
    fontSize: 14,
  },
  switchRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    padding: spacing.sm,
    backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.md,
    marginTop: spacing.md,
  },
  switchLabel: { color: colors.onSurface, fontSize: 14, fontWeight: "700" },
  switchHint: { color: colors.muted, fontSize: 11, marginTop: 2 },
  primaryBtn: {
    marginTop: spacing.lg,
    backgroundColor: colors.brandPrimary,
    padding: spacing.md,
    borderRadius: radius.md,
    alignItems: "center",
  },
  primaryBtnText: { color: colors.onBrandPrimary, fontWeight: "800", fontSize: 14 },
});
