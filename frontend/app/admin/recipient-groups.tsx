import { useCallback, useEffect, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ScrollView,
  TextInput,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { colors, spacing, radius } from "@/src/theme";

export default function RecipientGroups() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<string | null>(null); // group id being edited
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ name: "", emails: "" });

  const load = useCallback(async () => {
    try {
      setItems(await api.listGroups());
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const startNew = () => {
    setEditing("new");
    setForm({ name: "", emails: "" });
  };

  const startEdit = (g: any) => {
    setEditing(g.id);
    setForm({ name: g.name, emails: (g.emails || []).join(", ") });
  };

  const save = async () => {
    if (!form.name.trim()) return;
    setSaving(true);
    const emails = form.emails
      .split(",")
      .map((e) => e.trim())
      .filter((e) => e.length > 0);
    try {
      if (editing === "new") {
        await api.createGroup({ name: form.name.trim(), emails });
      } else if (editing) {
        await api.updateGroup(editing, { name: form.name.trim(), emails });
      }
      setEditing(null);
      setForm({ name: "", emails: "" });
      await load();
    } finally {
      setSaving(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.surface }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} testID="groups-back">
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Recipient Groups</Text>
        <Pressable onPress={startNew} testID="group-add">
          <Ionicons name="add" size={22} color={colors.brandPrimary} />
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: (insets.bottom || 0) + 40 }}
        keyboardShouldPersistTaps="handled"
      >
        {editing ? (
          <View style={styles.form} testID="group-form">
            <Text style={styles.formTitle}>
              {editing === "new" ? "New group" : "Edit group"}
            </Text>
            <TextInput
              testID="group-name"
              value={form.name}
              onChangeText={(t) => setForm((f) => ({ ...f, name: t }))}
              placeholder="Group name (e.g. Owners, Ops, Subs)"
              placeholderTextColor={colors.muted}
              style={styles.input}
            />
            <TextInput
              testID="group-emails"
              value={form.emails}
              onChangeText={(t) => setForm((f) => ({ ...f, emails: t }))}
              placeholder="owner@company.com, ops@company.com"
              placeholderTextColor={colors.muted}
              autoCapitalize="none"
              keyboardType="email-address"
              multiline
              style={[styles.input, { minHeight: 80, textAlignVertical: "top" }]}
            />
            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              <Pressable
                testID="group-cancel"
                onPress={() => setEditing(null)}
                style={[styles.btn, { backgroundColor: colors.surfaceTertiary, flex: 1 }]}
              >
                <Text style={{ color: colors.onSurface, fontWeight: "700" }}>Cancel</Text>
              </Pressable>
              <Pressable
                testID="group-save"
                onPress={save}
                disabled={saving || !form.name.trim()}
                style={[
                  styles.btn,
                  { backgroundColor: colors.brandPrimary, flex: 1 },
                  (saving || !form.name.trim()) && { opacity: 0.6 },
                ]}
              >
                {saving ? (
                  <ActivityIndicator color={colors.onBrandPrimary} />
                ) : (
                  <Text style={{ color: colors.onBrandPrimary, fontWeight: "700" }}>Save</Text>
                )}
              </Pressable>
            </View>
          </View>
        ) : null}

        {loading ? (
          <ActivityIndicator color={colors.brandPrimary} />
        ) : items.length === 0 ? (
          <View style={styles.empty}>
            <Ionicons name="mail-open" size={40} color={colors.muted} />
            <Text style={styles.emptyText}>No groups yet</Text>
            <Text style={styles.emptySub}>
              Save groups like "Owners" or "Subs" — pick one from Reports & Digest instead of typing every email.
            </Text>
          </View>
        ) : (
          items.map((g) => (
            <View key={g.id} style={styles.card} testID={`group-card-${g.id}`}>
              <View style={styles.iconBox}>
                <Ionicons name="people" size={18} color={colors.onBrandTertiary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.name}>{g.name}</Text>
                <Text style={styles.emailsText} numberOfLines={2}>
                  {(g.emails || []).join(", ") || "No emails"}
                </Text>
              </View>
              <Pressable
                testID={`group-edit-${g.id}`}
                onPress={() => startEdit(g)}
                style={styles.smallIconBtn}
              >
                <Ionicons name="create" size={16} color={colors.brandPrimary} />
              </Pressable>
              <Pressable
                testID={`group-delete-${g.id}`}
                onPress={async () => {
                  await api.deleteGroup(g.id).catch(() => {});
                  await load();
                }}
                style={[styles.smallIconBtn, { backgroundColor: "#FEE2E2" }]}
              >
                <Ionicons name="trash" size={16} color={colors.error} />
              </Pressable>
            </View>
          ))
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
  },
  headerTitle: { fontSize: 17, fontWeight: "700", color: colors.onSurface },
  form: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
    gap: spacing.sm,
    marginBottom: spacing.lg,
  },
  formTitle: { fontWeight: "700", color: colors.onSurface, fontSize: 16, marginBottom: spacing.sm },
  input: {
    backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.md,
    padding: spacing.md,
    color: colors.onSurface,
    borderWidth: 1,
    borderColor: colors.border,
    fontSize: 14,
  },
  btn: { padding: spacing.md, borderRadius: radius.md, alignItems: "center" },
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
  iconBox: {
    width: 36,
    height: 36,
    borderRadius: radius.md,
    backgroundColor: colors.brandTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
  name: { fontWeight: "700", color: colors.onSurface, fontSize: 14 },
  emailsText: { color: colors.muted, fontSize: 12, marginTop: 2 },
  smallIconBtn: {
    width: 32,
    height: 32,
    borderRadius: radius.md,
    backgroundColor: colors.brandTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
});
