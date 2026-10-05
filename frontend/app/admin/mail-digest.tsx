import { useEffect, useState } from "react";
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
  Switch,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { colors, spacing, radius } from "@/src/theme";

type AmPm = "AM" | "PM";

function to12h(h24: number): { h: string; ampm: AmPm } {
  const ampm: AmPm = h24 >= 12 ? "PM" : "AM";
  let h = h24 % 12;
  if (h === 0) h = 12;
  return { h: String(h), ampm };
}

function to24h(h12: string, ampm: AmPm): number {
  let h = parseInt(h12 || "0", 10);
  if (isNaN(h)) h = 0;
  if (ampm === "AM") {
    if (h === 12) h = 0;
  } else {
    if (h !== 12) h += 12;
  }
  return Math.max(0, Math.min(23, h));
}

export default function MailDigestAdmin() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [hour12, setHour12] = useState("7");
  const [ampm, setAmPm] = useState<AmPm>("AM");
  const [minute, setMinute] = useState("0");

  useEffect(() => {
    (async () => {
      try {
        const s = await api.getMailSchedule();
        setEnabled(!!s.enabled);
        const t = to12h(Number(s.hour ?? 7));
        setHour12(t.h);
        setAmPm(t.ampm);
        setMinute(String(s.minute ?? 0));
      } catch {}
      setLoading(false);
    })();
  }, []);

  const save = async () => {
    setMsg(null);
    setSaving(true);
    try {
      const hour = to24h(hour12, ampm);
      let m = parseInt(minute || "0", 10);
      if (isNaN(m)) m = 0;
      m = Math.max(0, Math.min(59, m));
      await api.setMailSchedule({ enabled, hour, minute: m });
      setMsg(enabled ? "Saved — digest will send daily." : "Saved — digest paused.");
    } catch (e: any) {
      setMsg(e?.message || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const sendNow = async () => {
    setMsg(null);
    setSending(true);
    try {
      const r = await api.sendMailDigestNow();
      setMsg(
        r.emails_sent > 0
          ? `Sent ${r.emails_sent} digest email${r.emails_sent === 1 ? "" : "s"} covering ${r.replies} repl${r.replies === 1 ? "y" : "ies"}.`
          : "No unread replies from the last 24h — nothing to send.",
      );
    } catch (e: any) {
      setMsg(e?.message || "Send failed");
    } finally {
      setSending(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.surface }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} testID="mail-digest-back">
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Daily Mail Digest</Text>
        <View style={{ width: 26 }} />
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 80 }}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.card}>
          <Text style={styles.cardTitle}>What it does</Text>
          <Text style={styles.cardBody}>
            Every morning at the time you choose, Summar-Eeze emails each report author a
            single digest listing their <Text style={{ fontWeight: "700" }}>unread replies
            from the last 24 hours</Text>, grouped by report → job. If there's nothing new,
            no email is sent.
          </Text>
        </View>

        {loading ? (
          <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />
        ) : (
          <>
            <View style={styles.card}>
              <View style={styles.toggleRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.cardTitle}>Enable daily digest</Text>
                  <Text style={styles.cardSub}>Turn on to send automatically each morning.</Text>
                </View>
                <Switch
                  testID="mail-digest-enable"
                  value={enabled}
                  onValueChange={setEnabled}
                  trackColor={{ true: colors.brandPrimary, false: colors.borderStrong }}
                />
              </View>
            </View>

            <View style={styles.card}>
              <Text style={styles.cardTitle}>Send time</Text>
              <View style={styles.timeRow}>
                <TextInput
                  testID="mail-digest-hour"
                  value={hour12}
                  onChangeText={(t) => setHour12(t.replace(/[^0-9]/g, "").slice(0, 2))}
                  keyboardType="number-pad"
                  placeholder="7"
                  placeholderTextColor={colors.muted}
                  style={styles.timeInput}
                />
                <Text style={styles.timeSep}>:</Text>
                <TextInput
                  testID="mail-digest-minute"
                  value={minute.padStart(2, "0")}
                  onChangeText={(t) => setMinute(t.replace(/[^0-9]/g, "").slice(0, 2))}
                  keyboardType="number-pad"
                  placeholder="00"
                  placeholderTextColor={colors.muted}
                  style={styles.timeInput}
                />
                <View style={styles.ampmRow}>
                  <Pressable
                    testID="mail-digest-am"
                    onPress={() => setAmPm("AM")}
                    style={[styles.ampmChip, ampm === "AM" && styles.ampmChipActive]}
                  >
                    <Text style={[styles.ampmText, ampm === "AM" && styles.ampmTextActive]}>AM</Text>
                  </Pressable>
                  <Pressable
                    testID="mail-digest-pm"
                    onPress={() => setAmPm("PM")}
                    style={[styles.ampmChip, ampm === "PM" && styles.ampmChipActive]}
                  >
                    <Text style={[styles.ampmText, ampm === "PM" && styles.ampmTextActive]}>PM</Text>
                  </Pressable>
                </View>
              </View>
              <Text style={styles.cardSub}>Server time zone (UTC).</Text>
            </View>

            {msg ? (
              <Text style={styles.msg} testID="mail-digest-msg">
                {msg}
              </Text>
            ) : null}

            <Pressable
              testID="mail-digest-save"
              onPress={save}
              disabled={saving}
              style={({ pressed }) => [
                styles.primaryBtn,
                pressed && { opacity: 0.85 },
                saving && { opacity: 0.7 },
              ]}
            >
              {saving ? (
                <ActivityIndicator color={colors.onBrandPrimary} />
              ) : (
                <>
                  <Ionicons name="save" size={16} color={colors.onBrandPrimary} />
                  <Text style={styles.primaryBtnText}>Save schedule</Text>
                </>
              )}
            </Pressable>

            <Pressable
              testID="mail-digest-send-now"
              onPress={sendNow}
              disabled={sending}
              style={({ pressed }) => [
                styles.secondaryBtn,
                pressed && { opacity: 0.85 },
                sending && { opacity: 0.7 },
              ]}
            >
              {sending ? (
                <ActivityIndicator color={colors.brandPrimary} />
              ) : (
                <>
                  <Ionicons name="send" size={14} color={colors.brandPrimary} />
                  <Text style={styles.secondaryBtnText}>Send now (test)</Text>
                </>
              )}
            </Pressable>
          </>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
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
  card: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  cardTitle: { color: colors.onSurface, fontWeight: "700", fontSize: 14 },
  cardSub: { color: colors.muted, fontSize: 12, marginTop: 4 },
  cardBody: {
    color: colors.onSurfaceTertiary,
    fontSize: 13,
    lineHeight: 19,
    marginTop: 6,
  },
  toggleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
  },
  timeRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    marginTop: 8,
    marginBottom: 4,
  },
  timeInput: {
    width: 54,
    backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.md,
    paddingVertical: 10,
    paddingHorizontal: 10,
    textAlign: "center",
    color: colors.onSurface,
    borderWidth: 1,
    borderColor: colors.border,
    fontSize: 15,
    fontWeight: "700",
  },
  timeSep: { color: colors.onSurface, fontSize: 20, fontWeight: "700" },
  ampmRow: { flexDirection: "row", gap: 6, marginLeft: 6 },
  ampmChip: {
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceTertiary,
  },
  ampmChipActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  ampmText: { color: colors.onSurface, fontWeight: "700", fontSize: 12 },
  ampmTextActive: { color: colors.onBrandPrimary },
  msg: { color: colors.onSurfaceTertiary, fontSize: 13, marginBottom: spacing.sm },
  primaryBtn: {
    marginTop: spacing.sm,
    backgroundColor: colors.brandPrimary,
    padding: spacing.md + 2,
    borderRadius: radius.md,
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "center",
    gap: spacing.xs,
  },
  primaryBtnText: { color: colors.onBrandPrimary, fontWeight: "700", fontSize: 15 },
  secondaryBtn: {
    marginTop: spacing.md,
    paddingVertical: 10,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.brandPrimary,
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "center",
    gap: 6,
  },
  secondaryBtnText: { color: colors.brandPrimary, fontWeight: "700", fontSize: 13 },
});
