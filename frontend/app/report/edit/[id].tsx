import { useEffect, useState } from "react";
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TextInput,
  Pressable,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { colors, spacing, radius } from "@/src/theme";

export default function EditReport() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    project_name: "",
    project_code: "",
    highlights: "",
    delays: "",
    change_orders: "",
    material_notes: "",
  });

  useEffect(() => {
    if (!id) return;
    api
      .getReport(id)
      .then((r) => {
        setForm({
          project_name: r.project_name || "",
          project_code: r.project_code || "",
          highlights: r.highlights || "",
          delays: r.delays || "",
          change_orders: r.change_orders || "",
          material_notes: r.material_notes || "",
        });
      })
      .finally(() => setLoading(false));
  }, [id]);

  const save = async () => {
    setError(null);
    setSaving(true);
    try {
      await api.patchReport(id!, form);
      router.back();
    } catch (e: any) {
      setError(e.message || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.brandPrimary} />
      </View>
    );
  }

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.surface }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} testID="edit-back">
          <Ionicons name="close" size={26} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Edit Report</Text>
        <View style={{ width: 26 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg }} keyboardShouldPersistTaps="handled">
        <Field label="Project name" value={form.project_name} onChange={(t) => setForm((f) => ({ ...f, project_name: t }))} testID="edit-project-name" />
        <Field label="Project code" value={form.project_code} onChange={(t) => setForm((f) => ({ ...f, project_code: t }))} testID="edit-project-code" />
        <Field label="Highlights" value={form.highlights} onChange={(t) => setForm((f) => ({ ...f, highlights: t }))} multiline testID="edit-highlights" />
        <Field label="Delays" value={form.delays} onChange={(t) => setForm((f) => ({ ...f, delays: t }))} multiline testID="edit-delays" />
        <Field label="Change orders" value={form.change_orders} onChange={(t) => setForm((f) => ({ ...f, change_orders: t }))} multiline testID="edit-change-orders" />
        <Field label="Material notes" value={form.material_notes} onChange={(t) => setForm((f) => ({ ...f, material_notes: t }))} multiline testID="edit-material-notes" />

        {error ? <Text style={styles.error}>{error}</Text> : null}
        <Pressable
          testID="edit-save"
          onPress={save}
          disabled={saving}
          style={({ pressed }) => [
            styles.primaryBtn,
            pressed && { opacity: 0.85 },
            saving && { opacity: 0.7 },
          ]}
        >
          {saving ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.primaryBtnText}>Save</Text>}
        </Pressable>
        <Text style={styles.note}>
          Editing the report body does NOT regenerate the AI summary. Create a new report to re-run AI.
        </Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function Field({
  label,
  value,
  onChange,
  multiline,
  testID,
}: {
  label: string;
  value: string;
  onChange: (t: string) => void;
  multiline?: boolean;
  testID: string;
}) {
  return (
    <View>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        testID={testID}
        value={value}
        onChangeText={onChange}
        multiline={multiline}
        placeholderTextColor={colors.muted}
        style={[styles.input, multiline && { minHeight: 80, textAlignVertical: "top" }]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
  },
  headerTitle: { fontSize: 17, fontWeight: "700", color: colors.onSurface },
  label: {
    color: colors.onSurfaceTertiary,
    fontSize: 13,
    fontWeight: "700",
    marginTop: spacing.md,
    marginBottom: spacing.xs,
  },
  input: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    padding: spacing.md,
    color: colors.onSurface,
    borderWidth: 1,
    borderColor: colors.border,
    fontSize: 14,
  },
  primaryBtn: {
    marginTop: spacing.lg,
    backgroundColor: colors.brandPrimary,
    padding: spacing.md + 2,
    borderRadius: radius.md,
    alignItems: "center",
  },
  primaryBtnText: { color: colors.onBrandPrimary, fontWeight: "700", fontSize: 15 },
  note: { color: colors.muted, fontSize: 11, marginTop: spacing.md, textAlign: "center" },
  error: { color: colors.error, marginTop: spacing.md, fontSize: 13 },
});
