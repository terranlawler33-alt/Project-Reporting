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

export default function CustomersScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    name: "",
    address: "",
    phone: "",
    email: "",
    project_code: "",
    notes: "",
  });

  const load = useCallback(async () => {
    try {
      setItems(await api.listCustomers());
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    if (!form.name) return;
    setSaving(true);
    try {
      await api.createCustomer({
        name: form.name,
        address: form.address || null,
        phone: form.phone || null,
        email: form.email || null,
        project_code: form.project_code || null,
        notes: form.notes || null,
      });
      setForm({ name: "", address: "", phone: "", email: "", project_code: "", notes: "" });
      setShowForm(false);
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
        <Pressable onPress={() => router.back()} testID="customers-back">
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Customer Directory</Text>
        <Pressable onPress={() => setShowForm((s) => !s)} testID="customers-add-toggle">
          <Ionicons name={showForm ? "close" : "add"} size={22} color={colors.brandPrimary} />
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: (insets.bottom || 0) + 40 }}
        keyboardShouldPersistTaps="handled"
      >
        {showForm && (
          <View style={styles.form} testID="new-customer-form">
            <Text style={styles.formTitle}>New Customer</Text>
            <TextInput
              testID="customer-name"
              value={form.name}
              onChangeText={(t) => setForm((f) => ({ ...f, name: t }))}
              placeholder="Customer name"
              placeholderTextColor={colors.muted}
              style={styles.input}
            />
            <TextInput
              testID="customer-address"
              value={form.address}
              onChangeText={(t) => setForm((f) => ({ ...f, address: t }))}
              placeholder="Address"
              placeholderTextColor={colors.muted}
              style={styles.input}
            />
            <TextInput
              testID="customer-phone"
              value={form.phone}
              onChangeText={(t) => setForm((f) => ({ ...f, phone: t }))}
              placeholder="Phone"
              placeholderTextColor={colors.muted}
              keyboardType="phone-pad"
              style={styles.input}
            />
            <TextInput
              testID="customer-email"
              value={form.email}
              onChangeText={(t) => setForm((f) => ({ ...f, email: t }))}
              placeholder="Email"
              placeholderTextColor={colors.muted}
              autoCapitalize="none"
              keyboardType="email-address"
              style={styles.input}
            />
            <TextInput
              testID="customer-project"
              value={form.project_code}
              onChangeText={(t) => setForm((f) => ({ ...f, project_code: t }))}
              placeholder="Project code"
              placeholderTextColor={colors.muted}
              style={styles.input}
            />
            <TextInput
              testID="customer-notes"
              value={form.notes}
              onChangeText={(t) => setForm((f) => ({ ...f, notes: t }))}
              placeholder="Notes / preferences / troublesome-flag"
              placeholderTextColor={colors.muted}
              multiline
              style={[styles.input, { minHeight: 70, textAlignVertical: "top" }]}
            />
            <Pressable
              testID="customer-save"
              onPress={save}
              disabled={saving || !form.name}
              style={({ pressed }) => [
                styles.primaryBtn,
                pressed && { opacity: 0.85 },
                (saving || !form.name) && { opacity: 0.6 },
              ]}
            >
              {saving ? (
                <ActivityIndicator color={colors.onBrandPrimary} />
              ) : (
                <Text style={styles.primaryBtnText}>Save Customer</Text>
              )}
            </Pressable>
          </View>
        )}

        {loading ? (
          <ActivityIndicator color={colors.brandPrimary} />
        ) : items.length === 0 ? (
          <View style={styles.empty}>
            <Ionicons name="people-outline" size={40} color={colors.muted} />
            <Text style={styles.emptyText}>No customers yet</Text>
            <Text style={styles.emptySub}>Add customers so crews pick from a list.</Text>
          </View>
        ) : (
          items.map((c) => (
            <View key={c.id} style={styles.card} testID={`customer-card-${c.id}`}>
              <View style={styles.cardIcon}>
                <Ionicons name="person" size={18} color={colors.onBrandTertiary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.cardName}>
                  {c.name} {c.project_code ? `· ${c.project_code}` : ""}
                </Text>
                {c.address ? <Text style={styles.cardMeta}>{c.address}</Text> : null}
                {c.phone || c.email ? (
                  <Text style={styles.cardMeta}>
                    {c.phone || ""} {c.email ? `· ${c.email}` : ""}
                  </Text>
                ) : null}
                {c.notes ? <Text style={styles.cardNotes}>{c.notes}</Text> : null}
              </View>
              <Pressable
                testID={`customer-delete-${c.id}`}
                onPress={async () => {
                  await api.deleteCustomer(c.id).catch(() => {});
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
  primaryBtn: {
    marginTop: spacing.sm,
    backgroundColor: colors.brandPrimary,
    padding: spacing.md,
    borderRadius: radius.md,
    alignItems: "center",
  },
  primaryBtnText: { color: colors.onBrandPrimary, fontWeight: "700" },
  empty: {
    padding: spacing.xxl,
    alignItems: "center",
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  emptyText: { fontWeight: "700", color: colors.onSurface, marginTop: spacing.sm },
  emptySub: { color: colors.muted, fontSize: 12, marginTop: spacing.xs },
  card: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.md,
    padding: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.sm,
  },
  cardIcon: {
    width: 36,
    height: 36,
    borderRadius: radius.md,
    backgroundColor: colors.brandTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
  cardName: { fontWeight: "700", color: colors.onSurface, fontSize: 14 },
  cardMeta: { color: colors.muted, fontSize: 12, marginTop: 2 },
  cardNotes: { color: colors.onSurfaceTertiary, fontSize: 12, marginTop: 4, fontStyle: "italic" },
  deleteBtn: { padding: spacing.sm, borderRadius: radius.md, backgroundColor: "#FEE2E2" },
});
