import { useState } from "react";
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

export default function WeeklyDigest() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [emails, setEmails] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);

  const send = async () => {
    setError(null);
    setResult(null);
    const list = emails
      .split(",")
      .map((e) => e.trim())
      .filter((e) => e.length > 0);
    if (list.length === 0) {
      setError("Add at least one recipient email");
      return;
    }
    setLoading(true);
    try {
      const r = await api.sendWeeklyDigest(list);
      setResult(r);
    } catch (e: any) {
      setError(e.message || "Failed to generate digest");
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.surface }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} testID="digest-back">
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Weekly Digest</Text>
        <View style={{ width: 26 }} />
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: (insets.bottom || 0) + 40 }}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.card}>
          <Ionicons name="calendar" size={28} color={colors.brandPrimary} />
          <Text style={styles.cardTitle}>Roll up the last 7 days</Text>
          <Text style={styles.cardSub}>
            GPT 5.4 will summarize every report from the past week: top wins, delays, change
            orders, escalations, weather impact, and next-week actions.
          </Text>
        </View>

        <Text style={styles.label}>Recipient emails (comma-separated)</Text>
        <TextInput
          testID="digest-emails"
          value={emails}
          onChangeText={setEmails}
          placeholder="owner@company.com, ops@company.com"
          placeholderTextColor={colors.muted}
          autoCapitalize="none"
          keyboardType="email-address"
          style={styles.input}
        />

        {error ? (
          <Text style={styles.error} testID="digest-error">
            {error}
          </Text>
        ) : null}

        <Pressable
          testID="digest-send"
          onPress={send}
          disabled={loading}
          style={({ pressed }) => [
            styles.primaryBtn,
            pressed && { opacity: 0.85 },
            loading && { opacity: 0.7 },
          ]}
        >
          {loading ? (
            <>
              <ActivityIndicator color={colors.onBrandPrimary} />
              <Text style={styles.primaryBtnText}>Generating digest…</Text>
            </>
          ) : (
            <>
              <Ionicons name="mail" size={18} color={colors.onBrandPrimary} />
              <Text style={styles.primaryBtnText}>Generate & Email</Text>
            </>
          )}
        </Pressable>

        {result ? (
          <View style={styles.resultCard} testID="digest-result">
            <View style={styles.resultHeader}>
              <Ionicons name="checkmark-circle" size={20} color={colors.success} />
              <Text style={styles.resultTitle}>Digest sent</Text>
            </View>
            <Text style={styles.resultMeta}>
              To: {result.email_sent_to?.join(", ") || "—"}
            </Text>
            <Text style={styles.resultMeta}>
              Reports rolled: {result.report_ids?.length ?? 0} · Visits: {result.totals?.visits ?? 0} ·
              Breaks: {result.totals?.breaks ?? 0} · Comms: {result.totals?.sms ?? 0}
            </Text>
            <Text style={styles.resultBody}>{result.text}</Text>
          </View>
        ) : null}
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
  card: {
    backgroundColor: colors.brandTertiary,
    borderRadius: radius.md,
    padding: spacing.lg,
    gap: spacing.xs,
  },
  cardTitle: { fontWeight: "700", color: colors.onBrandTertiary, fontSize: 16, marginTop: spacing.xs },
  cardSub: { color: colors.onBrandTertiary, fontSize: 13, lineHeight: 18 },
  label: {
    color: colors.onSurfaceTertiary,
    fontSize: 13,
    fontWeight: "700",
    marginTop: spacing.lg,
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
  error: { color: colors.error, marginTop: spacing.md, fontSize: 13 },
  primaryBtn: {
    marginTop: spacing.lg,
    backgroundColor: colors.brandPrimary,
    padding: spacing.md + 2,
    borderRadius: radius.md,
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "center",
    gap: spacing.sm,
  },
  primaryBtnText: { color: colors.onBrandPrimary, fontWeight: "700", fontSize: 15 },
  resultCard: {
    marginTop: spacing.lg,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  resultHeader: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  resultTitle: { fontWeight: "700", color: colors.onSurface, fontSize: 15 },
  resultMeta: { color: colors.muted, fontSize: 12, marginTop: 4 },
  resultBody: { color: colors.onSurface, fontSize: 14, lineHeight: 21, marginTop: spacing.md },
});
