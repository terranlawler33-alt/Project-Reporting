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
import { SmsImportSheet } from "@/src/components/SmsImportSheet";
import { DeviceSms, isSmsAvailable } from "@/src/sms";
import { colors, spacing, radius } from "@/src/theme";

const CATEGORIES = [
  "project_detail",
  "change_order",
  "escalation",
  "schedule",
  "weather_delay",
  "material",
  "traffic",
  "other",
];
const CHANNELS = ["SMS", "Call", "Email"];
const DIRS = ["inbound", "outbound"];

export default function SmsLog() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [importing, setImporting] = useState(false);
  const [form, setForm] = useState({
    contact_name: "",
    contact_role: "",
    channel: "SMS",
    direction: "inbound",
    category: "project_detail",
    content: "",
    project_code: "",
  });

  const load = useCallback(async () => {
    try {
      setItems(await api.smsToday());
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    setSaving(true);
    try {
      await api.createSms(form);
      setForm({
        contact_name: "",
        contact_role: "",
        channel: "SMS",
        direction: "inbound",
        category: "project_detail",
        content: "",
        project_code: "",
      });
      setShowForm(false);
      await load();
    } finally {
      setSaving(false);
    }
  };

  const importFromPhone = async (msgs: DeviceSms[]) => {
    if (msgs.length === 0) return;
    setImporting(true);
    try {
      const items = msgs.map((m) => ({
        contact_name: m.display_name || m.address || "Unknown",
        contact_role: "Imported SMS",
        channel: "SMS",
        direction: "inbound",
        category: "other",
        content: m.body,
        project_code: null,
      }));
      await api.createSmsBulk(items);
      await load();
    } finally {
      setImporting(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.surface }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} testID="sms-back">
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Communications Log</Text>
        <Pressable onPress={() => setShowForm((s) => !s)} testID="sms-add-toggle">
          <Ionicons name={showForm ? "close" : "add"} size={22} color={colors.brandPrimary} />
        </Pressable>
      </View>

      <View style={styles.importBar}>
        <Pressable
          testID="sms-import-open"
          onPress={() => setShowImport(true)}
          disabled={importing}
          style={({ pressed }) => [
            styles.importBtn,
            pressed && { opacity: 0.85 },
            !isSmsAvailable() && styles.importBtnDisabled,
            importing && { opacity: 0.7 },
          ]}
        >
          {importing ? (
            <ActivityIndicator color={isSmsAvailable() ? colors.onBrandPrimary : colors.muted} size="small" />
          ) : (
            <Ionicons
              name="phone-portrait"
              size={16}
              color={isSmsAvailable() ? colors.onBrandPrimary : colors.muted}
            />
          )}
          <Text style={[styles.importBtnText, !isSmsAvailable() && { color: colors.muted }]}>
            {importing ? "Importing…" : "Import from phone"}
          </Text>
        </Pressable>
        {!isSmsAvailable() ? (
          <Text style={styles.importHint}>Android only — Apple blocks SMS access on iPhone.</Text>
        ) : (
          <Text style={styles.importHint}>Pull texts from the last 7 days into today's log.</Text>
        )}
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: (insets.bottom || 0) + 40 }}
        keyboardShouldPersistTaps="handled"
      >
        {showForm && (
          <View style={styles.form} testID="new-sms-form">
            <TextInput
              testID="sms-contact-name"
              value={form.contact_name}
              onChangeText={(t) => setForm((f) => ({ ...f, contact_name: t }))}
              placeholder="Contact name"
              placeholderTextColor={colors.muted}
              style={styles.input}
            />
            <TextInput
              testID="sms-contact-role"
              value={form.contact_role}
              onChangeText={(t) => setForm((f) => ({ ...f, contact_role: t }))}
              placeholder="Role (Subcontractor, Customer, Supplier)"
              placeholderTextColor={colors.muted}
              style={styles.input}
            />
            <Row title="Channel" options={CHANNELS} value={form.channel} onChange={(v) => setForm((f) => ({ ...f, channel: v }))} testPrefix="sms-channel" />
            <Row title="Direction" options={DIRS} value={form.direction} onChange={(v) => setForm((f) => ({ ...f, direction: v }))} testPrefix="sms-dir" />
            <Text style={styles.label}>Category</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.xs, paddingRight: spacing.md }}>
              {CATEGORIES.map((c) => (
                <Pressable
                  key={c}
                  testID={`sms-cat-${c}`}
                  onPress={() => setForm((f) => ({ ...f, category: c }))}
                  style={[styles.chip, form.category === c && styles.chipActive, { flexShrink: 0 }]}
                >
                  <Text style={[styles.chipText, form.category === c && styles.chipTextActive]}>
                    {c.replace(/_/g, " ")}
                  </Text>
                </Pressable>
              ))}
            </ScrollView>
            <TextInput
              testID="sms-content"
              value={form.content}
              onChangeText={(t) => setForm((f) => ({ ...f, content: t }))}
              placeholder="Summary of communication"
              placeholderTextColor={colors.muted}
              multiline
              style={[styles.input, { minHeight: 90, textAlignVertical: "top" }]}
            />
            <TextInput
              testID="sms-project"
              value={form.project_code}
              onChangeText={(t) => setForm((f) => ({ ...f, project_code: t }))}
              placeholder="Project code (optional)"
              placeholderTextColor={colors.muted}
              style={styles.input}
            />
            <Pressable
              testID="sms-save"
              onPress={save}
              disabled={saving || !form.contact_name || !form.content}
              style={({ pressed }) => [
                styles.primaryBtn,
                pressed && { opacity: 0.85 },
                (saving || !form.contact_name || !form.content) && { opacity: 0.6 },
              ]}
            >
              {saving ? (
                <ActivityIndicator color={colors.onBrandPrimary} />
              ) : (
                <Text style={styles.primaryBtnText}>Log Communication</Text>
              )}
            </Pressable>
          </View>
        )}

        {loading ? (
          <ActivityIndicator color={colors.brandPrimary} />
        ) : items.length === 0 ? (
          <View style={styles.empty}>
            <Ionicons name="chatbubbles-outline" size={40} color={colors.muted} />
            <Text style={styles.emptyText}>No comms logged today</Text>
          </View>
        ) : (
          items.map((s) => (
            <View key={s.id} style={styles.item} testID={`sms-item-${s.id}`}>
              <Text style={styles.itemTitle}>
                {s.contact_name} · {s.contact_role}
              </Text>
              <Text style={styles.itemMeta}>
                {s.channel} {s.direction} · {s.category.replace(/_/g, " ")}
                {s.project_code ? ` · ${s.project_code}` : ""}
              </Text>
              <Text style={styles.itemContent}>{s.content}</Text>
              <Text style={styles.itemTime}>{new Date(s.timestamp).toLocaleTimeString()}</Text>
            </View>
          ))
        )}
      </ScrollView>

      <SmsImportSheet
        visible={showImport}
        onClose={() => setShowImport(false)}
        mode="sms-log"
        onImportItems={importFromPhone}
      />
    </KeyboardAvoidingView>
  );
}

function Row({
  title,
  options,
  value,
  onChange,
  testPrefix,
}: {
  title: string;
  options: string[];
  value: string;
  onChange: (v: string) => void;
  testPrefix: string;
}) {
  return (
    <View>
      <Text style={styles.label}>{title}</Text>
      <View style={{ flexDirection: "row", gap: spacing.xs }}>
        {options.map((o) => (
          <Pressable
            key={o}
            testID={`${testPrefix}-${o}`}
            onPress={() => onChange(o)}
            style={[styles.chip, value === o && styles.chipActive]}
          >
            <Text style={[styles.chipText, value === o && styles.chipTextActive]}>{o}</Text>
          </Pressable>
        ))}
      </View>
    </View>
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
  importBar: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: 2,
    backgroundColor: colors.surfaceSecondary,
    gap: 4,
  },
  importBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    alignSelf: "flex-start",
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.pill,
  },
  importBtnDisabled: {
    backgroundColor: colors.surfaceTertiary,
    borderWidth: 1,
    borderColor: colors.border,
  },
  importBtnText: { color: colors.onBrandPrimary, fontWeight: "700", fontSize: 12 },
  importHint: { color: colors.muted, fontSize: 11 },
  form: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
    gap: spacing.sm,
    marginBottom: spacing.lg,
  },
  input: {
    backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.md,
    padding: spacing.md,
    color: colors.onSurface,
    borderWidth: 1,
    borderColor: colors.border,
    fontSize: 14,
  },
  label: { color: colors.onSurfaceTertiary, fontSize: 12, fontWeight: "700", marginTop: spacing.xs, marginBottom: spacing.xs },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    height: 36,
    justifyContent: "center",
  },
  chipActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { color: colors.onSurface, fontWeight: "600", fontSize: 12 },
  chipTextActive: { color: colors.onBrandPrimary },
  primaryBtn: {
    marginTop: spacing.md,
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
  item: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.sm,
  },
  itemTitle: { fontWeight: "700", color: colors.onSurface, fontSize: 14 },
  itemMeta: { color: colors.muted, fontSize: 11, marginTop: 2 },
  itemContent: { color: colors.onSurfaceTertiary, fontSize: 13, marginTop: spacing.xs },
  itemTime: { color: colors.muted, fontSize: 11, marginTop: spacing.xs },
});
