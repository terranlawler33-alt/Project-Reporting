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

const ROLES = ["Owner", "Operations", "Sales", "Production", "Labor", "Project Manager"] as const;

export default function AdminUsers() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    email: "",
    password: "",
    name: "",
    role: "Production" as (typeof ROLES)[number],
    job_title: "",
    department: "",
    job_code: "",
    is_admin: false,
  });

  const load = useCallback(async () => {
    try {
      setUsers(await api.listUsers());
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    setError(null);
    setSaving(true);
    try {
      await api.createUser(form);
      setForm({
        email: "",
        password: "",
        name: "",
        role: "Production",
        job_title: "",
        department: "",
        job_code: "",
        is_admin: false,
      });
      setShowForm(false);
      await load();
    } catch (e: any) {
      setError(e.message || "Create user failed");
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
        <Pressable onPress={() => router.back()} testID="admin-back">
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Manage Users</Text>
        <Pressable onPress={() => setShowForm((s) => !s)} testID="admin-add-toggle">
          <Ionicons name={showForm ? "close" : "person-add"} size={22} color={colors.brandPrimary} />
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: (insets.bottom || 0) + 40 }}
        keyboardShouldPersistTaps="handled"
      >
        {showForm && (
          <View style={styles.form} testID="new-user-form">
            <Text style={styles.formTitle}>Create User</Text>
            <TextInput
              testID="new-user-name"
              value={form.name}
              onChangeText={(t) => setForm((f) => ({ ...f, name: t }))}
              placeholder="Full name"
              placeholderTextColor={colors.muted}
              style={styles.input}
            />
            <TextInput
              testID="new-user-email"
              value={form.email}
              onChangeText={(t) => setForm((f) => ({ ...f, email: t }))}
              placeholder="Email"
              placeholderTextColor={colors.muted}
              autoCapitalize="none"
              keyboardType="email-address"
              style={styles.input}
            />
            <TextInput
              testID="new-user-password"
              value={form.password}
              onChangeText={(t) => setForm((f) => ({ ...f, password: t }))}
              placeholder="Temporary password (min 6)"
              placeholderTextColor={colors.muted}
              secureTextEntry
              style={styles.input}
            />
            <Text style={styles.label}>Role</Text>
            <View style={styles.chipRow}>
              {ROLES.map((r) => (
                <Pressable
                  key={r}
                  testID={`role-${r}`}
                  onPress={() => setForm((f) => ({ ...f, role: r }))}
                  style={[styles.chip, form.role === r && styles.chipActive]}
                >
                  <Text style={[styles.chipText, form.role === r && styles.chipTextActive]}>
                    {r}
                  </Text>
                </Pressable>
              ))}
            </View>
            <TextInput
              testID="new-user-title"
              value={form.job_title}
              onChangeText={(t) => setForm((f) => ({ ...f, job_title: t }))}
              placeholder="Job title"
              placeholderTextColor={colors.muted}
              style={styles.input}
            />
            <TextInput
              testID="new-user-dept"
              value={form.department}
              onChangeText={(t) => setForm((f) => ({ ...f, department: t }))}
              placeholder="Department"
              placeholderTextColor={colors.muted}
              style={styles.input}
            />
            <TextInput
              testID="new-user-code"
              value={form.job_code}
              onChangeText={(t) => setForm((f) => ({ ...f, job_code: t }))}
              placeholder="Job code (e.g. PM-001)"
              placeholderTextColor={colors.muted}
              style={styles.input}
            />
            <Pressable
              testID="toggle-admin"
              onPress={() => setForm((f) => ({ ...f, is_admin: !f.is_admin }))}
              style={styles.adminToggle}
            >
              <Ionicons
                name={form.is_admin ? "checkbox" : "square-outline"}
                size={22}
                color={colors.brandPrimary}
              />
              <Text style={styles.adminToggleText}>Grant admin rights</Text>
            </Pressable>
            {error ? <Text style={styles.error}>{error}</Text> : null}
            <Pressable
              testID="new-user-save"
              onPress={save}
              disabled={saving || !form.email || !form.password || !form.name}
              style={({ pressed }) => [
                styles.primaryBtn,
                pressed && { opacity: 0.85 },
                (saving || !form.email || !form.password || !form.name) && { opacity: 0.6 },
              ]}
            >
              {saving ? (
                <ActivityIndicator color={colors.onBrandPrimary} />
              ) : (
                <Text style={styles.primaryBtnText}>Create User</Text>
              )}
            </Pressable>
          </View>
        )}

        {loading ? (
          <ActivityIndicator color={colors.brandPrimary} />
        ) : (
          users.map((u) => (
            <View key={u.id} style={styles.userCard} testID={`user-card-${u.id}`}>
              <View style={styles.userIcon}>
                <Ionicons name="person" size={18} color={colors.onBrandTertiary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.userName}>
                  {u.name} {u.is_admin ? "· ADMIN" : ""}
                </Text>
                <Text style={styles.userMeta}>
                  {u.role} · {u.email}
                </Text>
                {u.job_title || u.job_code ? (
                  <Text style={styles.userMeta}>
                    {u.job_title || ""} {u.job_code ? `(${u.job_code})` : ""}
                  </Text>
                ) : null}
              </View>
              <Pressable
                testID={`delete-user-${u.id}`}
                onPress={async () => {
                  await api.deleteUser(u.id).catch(() => {});
                  await load();
                }}
                style={styles.deleteBtn}
              >
                <Ionicons name="trash-outline" size={16} color={colors.error} />
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
  label: { color: colors.onSurfaceTertiary, fontSize: 12, fontWeight: "700", marginTop: spacing.sm },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
  },
  chipActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { color: colors.onSurface, fontWeight: "600", fontSize: 12 },
  chipTextActive: { color: colors.onBrandPrimary },
  adminToggle: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  adminToggleText: { color: colors.onSurface, fontWeight: "600" },
  primaryBtn: {
    marginTop: spacing.md,
    backgroundColor: colors.brandPrimary,
    padding: spacing.md,
    borderRadius: radius.md,
    alignItems: "center",
  },
  primaryBtnText: { color: colors.onBrandPrimary, fontWeight: "700" },
  error: { color: colors.error, marginTop: spacing.sm, fontSize: 13 },
  userCard: {
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
  userIcon: {
    width: 36,
    height: 36,
    borderRadius: radius.md,
    backgroundColor: colors.brandTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
  userName: { fontWeight: "700", color: colors.onSurface, fontSize: 14 },
  userMeta: { color: colors.muted, fontSize: 12, marginTop: 2 },
  deleteBtn: {
    padding: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: "#FEE2E2",
  },
});
