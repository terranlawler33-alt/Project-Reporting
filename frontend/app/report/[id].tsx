import { useEffect, useRef, useState } from "react";
import { View, Text, ScrollView, StyleSheet, Pressable, ActivityIndicator, Platform, TextInput } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import Signature from "react-native-signature-canvas";
import { Image } from "expo-image";
import { api } from "@/src/api";
import { getToken } from "@/src/auth/storage";
import { colors, spacing, radius } from "@/src/theme";

export default function ReportDetail() {
  const insets = useSafeAreaInsets();
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [showSign, setShowSign] = useState(false);
  const [customerName, setCustomerName] = useState("");
  const [saving, setSaving] = useState(false);
  const sigRef = useRef<any>(null);

  const reload = async () => {
    if (!id) return;
    try {
      const r = await api.getReport(id);
      setReport(r);
    } catch {}
  };

  useEffect(() => {
    if (!id) return;
    reload().finally(() => setLoading(false));
  }, [id]);

  const downloadWorkday = async () => {
    const token = await getToken();
    const url = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api/reports/${id}/workday-export`;
    if (Platform.OS === "web") {
      const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      const blob = await res.blob();
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = `workday-${id}.csv`;
      a.click();
      URL.revokeObjectURL(objectUrl);
    } else {
      await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
    }
  };

  const onSignatureOK = async (dataUrl: string) => {
    if (!customerName.trim()) return;
    setSaving(true);
    try {
      const base64 = dataUrl.startsWith("data:") ? dataUrl : `data:image/png;base64,${dataUrl}`;
      await api.addSignature(id!, customerName.trim(), base64);
      await reload();
      setShowSign(false);
      setCustomerName("");
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
  if (!report) {
    return (
      <View style={styles.center}>
        <Text>Report not found</Text>
      </View>
    );
  }

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} testID="report-back">
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle} numberOfLines={1}>
          {report.report_date}
        </Text>
        <Pressable onPress={downloadWorkday} testID="workday-export">
          <Ionicons name="download" size={22} color={colors.brandPrimary} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: (insets.bottom || 0) + 100 }}>
        <View style={styles.aiTag}>
          <Ionicons name="sparkles" size={12} color={colors.onBrandTertiary} />
          <Text style={styles.aiTagText}>AI Summary</Text>
        </View>
        <Text style={styles.title}>{report.project_name || report.project_code || "Daily Report"}</Text>
        <Text style={styles.subtitle}>
          {report.author_name} · {report.author_role}
        </Text>

        {report.email_sent_to?.length ? (
          <View style={styles.emailSentBox} testID="email-sent-box">
            <Ionicons name="mail" size={14} color={colors.success} />
            <Text style={styles.emailSentText}>Sent to: {report.email_sent_to.join(", ")}</Text>
          </View>
        ) : null}

        <View style={styles.card}>
          <Text style={styles.summaryText}>{report.ai_summary}</Text>
        </View>

        {report.weather && (
          <MetaCard title="Weather" testID="report-weather">
            <Text style={styles.metaText}>
              {Math.round(report.weather.temperature_f)}°F · wind{" "}
              {Math.round(report.weather.wind_mph || 0)} mph · precip{" "}
              {(report.weather.precipitation || 0).toFixed(2)}"
            </Text>
          </MetaCard>
        )}

        {report.visits?.length ? (
          <MetaCard title={`Visits (${report.visits.length})`} testID="report-visits">
            {report.visits.map((v: any) => (
              <View key={v.id} style={styles.mini}>
                <Text style={styles.miniTitle}>{v.customer_name || "Job Site"}</Text>
                <Text style={styles.miniSub}>
                  {v.address || `${v.latitude?.toFixed?.(4)}, ${v.longitude?.toFixed?.(4)}`}
                </Text>
                {v.notes ? <Text style={styles.miniNotes}>{v.notes}</Text> : null}
              </View>
            ))}
          </MetaCard>
        ) : null}

        {report.breaks?.length ? (
          <MetaCard title={`Breaks (${report.breaks.length})`} testID="report-breaks">
            {report.breaks.map((b: any) => (
              <View key={b.id} style={styles.mini}>
                <Text style={styles.miniTitle}>
                  {b.break_type} · {b.duration_minutes ?? "?"} min
                </Text>
                <Text style={styles.miniSub}>{b.reason}</Text>
                {b.call_details ? <Text style={styles.miniNotes}>{b.call_details}</Text> : null}
              </View>
            ))}
          </MetaCard>
        ) : null}

        {report.sms_logs?.length ? (
          <MetaCard title={`Communications (${report.sms_logs.length})`} testID="report-sms">
            {report.sms_logs.map((s: any) => (
              <View key={s.id} style={styles.mini}>
                <Text style={styles.miniTitle}>
                  {s.contact_name} ({s.contact_role}) · {s.category}
                </Text>
                <Text style={styles.miniSub}>{s.channel} {s.direction}</Text>
                <Text style={styles.miniNotes}>{s.content}</Text>
              </View>
            ))}
          </MetaCard>
        ) : null}

        {/* Signature section */}
        <MetaCard title="Customer Sign-off" testID="report-signature">
          {report.signature ? (
            <View>
              <Text style={styles.miniTitle}>{report.signature.customer_name}</Text>
              <Text style={styles.miniSub}>
                Signed {new Date(report.signature.signed_at).toLocaleString()}
              </Text>
              <Image
                source={{ uri: report.signature.signature_base64 }}
                style={styles.signatureImage}
                contentFit="contain"
              />
            </View>
          ) : showSign ? (
            <View style={{ gap: spacing.sm }}>
              <TextInput
                testID="signature-customer-name"
                value={customerName}
                onChangeText={setCustomerName}
                placeholder="Customer name"
                placeholderTextColor={colors.muted}
                style={styles.sigInput}
              />
              <View style={styles.sigPadWrap}>
                <Signature
                  ref={sigRef}
                  onOK={onSignatureOK}
                  onEmpty={() => {}}
                  descriptionText="Sign above"
                  webStyle={sigWebStyle}
                  autoClear={false}
                  imageType="image/png"
                />
              </View>
              <View style={{ flexDirection: "row", gap: spacing.sm }}>
                <Pressable
                  testID="signature-cancel"
                  onPress={() => {
                    setShowSign(false);
                    setCustomerName("");
                  }}
                  style={[styles.smallBtn, { backgroundColor: colors.surfaceTertiary }]}
                >
                  <Text style={{ color: colors.onSurface, fontWeight: "700" }}>Cancel</Text>
                </Pressable>
                <Pressable
                  testID="signature-clear"
                  onPress={() => sigRef.current?.clearSignature?.()}
                  style={[styles.smallBtn, { backgroundColor: colors.surfaceTertiary }]}
                >
                  <Text style={{ color: colors.onSurface, fontWeight: "700" }}>Clear</Text>
                </Pressable>
                <Pressable
                  testID="signature-save"
                  onPress={() => sigRef.current?.readSignature?.()}
                  disabled={!customerName.trim() || saving}
                  style={[
                    styles.smallBtn,
                    { backgroundColor: colors.brandPrimary },
                    (!customerName.trim() || saving) && { opacity: 0.6 },
                  ]}
                >
                  {saving ? (
                    <ActivityIndicator color={colors.onBrandPrimary} size="small" />
                  ) : (
                    <Text style={{ color: colors.onBrandPrimary, fontWeight: "700" }}>Save</Text>
                  )}
                </Pressable>
              </View>
            </View>
          ) : (
            <Pressable
              testID="signature-start"
              onPress={() => setShowSign(true)}
              style={styles.signCTA}
            >
              <Ionicons name="create" size={16} color={colors.onBrandPrimary} />
              <Text style={{ color: colors.onBrandPrimary, fontWeight: "700" }}>
                Capture Customer Signature
              </Text>
            </Pressable>
          )}
        </MetaCard>
      </ScrollView>
    </View>
  );
}

const sigWebStyle = `
  .m-signature-pad { box-shadow: none; border: 1px solid #E5E7EB; border-radius: 12px; }
  .m-signature-pad--body { border: none; }
  .m-signature-pad--footer { display: none; margin: 0; }
  body,html { width: 100%; height: 100%; }
`;

function MetaCard({ title, children, testID }: { title: string; children: React.ReactNode; testID?: string }) {
  return (
    <View style={styles.metaCard} testID={testID}>
      <Text style={styles.metaTitle}>{title}</Text>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
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
  headerTitle: { fontSize: 17, fontWeight: "700", color: colors.onSurface, flex: 1, marginHorizontal: spacing.md },
  aiTag: {
    alignSelf: "flex-start",
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    backgroundColor: colors.brandTertiary,
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    borderRadius: radius.pill,
    marginBottom: spacing.sm,
  },
  aiTagText: { color: colors.onBrandTertiary, fontSize: 10, fontWeight: "700" },
  title: { fontSize: 22, fontWeight: "700", color: colors.onSurface },
  subtitle: { color: colors.muted, marginTop: 4 },
  emailSentBox: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "#DCFCE7",
    padding: spacing.sm,
    borderRadius: radius.md,
    marginTop: spacing.md,
  },
  emailSentText: { color: colors.success, fontWeight: "600", fontSize: 12 },
  card: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
    marginTop: spacing.lg,
  },
  summaryText: { color: colors.onSurface, fontSize: 15, lineHeight: 22 },
  metaCard: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
    marginTop: spacing.md,
  },
  metaTitle: {
    fontWeight: "700",
    color: colors.onSurface,
    fontSize: 14,
    marginBottom: spacing.sm,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  metaText: { color: colors.onSurfaceTertiary, fontSize: 13 },
  mini: {
    paddingVertical: spacing.sm,
    borderTopWidth: 0.5,
    borderTopColor: colors.divider,
  },
  miniTitle: { fontWeight: "700", color: colors.onSurface, fontSize: 13 },
  miniSub: { color: colors.muted, fontSize: 12, marginTop: 2 },
  miniNotes: { color: colors.onSurfaceTertiary, fontSize: 12, marginTop: 4, fontStyle: "italic" },
  signatureImage: {
    width: "100%",
    height: 160,
    backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.md,
    marginTop: spacing.sm,
  },
  sigInput: {
    backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.md,
    padding: spacing.md,
    color: colors.onSurface,
    borderWidth: 1,
    borderColor: colors.border,
    fontSize: 14,
  },
  sigPadWrap: {
    height: 220,
    borderRadius: radius.md,
    overflow: "hidden",
    backgroundColor: colors.surfaceTertiary,
  },
  smallBtn: {
    flex: 1,
    padding: spacing.sm + 2,
    borderRadius: radius.md,
    alignItems: "center",
  },
  signCTA: {
    flexDirection: "row",
    gap: spacing.sm,
    padding: spacing.md,
    backgroundColor: colors.brandPrimary,
    borderRadius: radius.md,
    alignItems: "center",
    justifyContent: "center",
  },
});
