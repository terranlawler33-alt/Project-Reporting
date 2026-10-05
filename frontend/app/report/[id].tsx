import { useEffect, useRef, useState } from "react";
import { View, Text, ScrollView, StyleSheet, Pressable, ActivityIndicator, Platform, TextInput, Share, Alert } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import Signature from "react-native-signature-canvas";
import { Image } from "expo-image";
import * as Clipboard from "expo-clipboard";
import { useAudioPlayer, useAudioPlayerStatus, setAudioModeAsync } from "expo-audio";
import { api } from "@/src/api";
import { getToken } from "@/src/auth/storage";
import { authedPhotoUrl } from "@/src/photos";
import { StructuredSummary } from "@/src/components/StructuredSummary";
import { priorityLevelColor } from "@/src/priority";
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
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [loadingTts, setLoadingTts] = useState(false);
  const [responses, setResponses] = useState<any[]>([]);
  const [editingSummaryFor, setEditingSummaryFor] = useState<string | null>(null);
  const [summaryDraft, setSummaryDraft] = useState("");
  const [savingSummary, setSavingSummary] = useState(false);
  const sigRef = useRef<any>(null);
  const player = useAudioPlayer(audioUrl ?? null);
  const playerStatus = useAudioPlayerStatus(player);

  const reload = async () => {
    if (!id) return;
    try {
      const r = await api.getReport(id);
      setReport(r);
    } catch {}
    try {
      const resps = await api.listReportResponses(id);
      setResponses(resps || []);
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

  const onShare = async () => {
    if (!report) return;
    let link = report.public_token
      ? `${process.env.EXPO_PUBLIC_BACKEND_URL}/api/public/reports/${report.public_token}`
      : "";
    if (!link) {
      try {
        const r = await api.createPortalLink(id!);
        link = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api/public/reports/${r.token}`;
        await reload();
      } catch {}
    }
    const body =
      `${report.project_name || report.project_code || "Daily Report"} — ${report.report_date}\n` +
      `From ${report.author_name} (${report.author_role})\n\n` +
      `${report.ai_summary}\n\n` +
      (link ? `View online: ${link}\n` : "");
    try {
      await Share.share({ message: body, title: `Daily Report — ${report.report_date}` });
    } catch {}
  };

  const generatePortalLink = async () => {
    try {
      await api.createPortalLink(id!);
      await reload();
    } catch {}
  };

  const revokePortalLink = async () => {
    try {
      await api.revokePortalLink(id!);
      await reload();
    } catch {}
  };

  const copyPortalLink = async () => {
    if (!report?.public_token) return;
    const link = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api/public/reports/${report.public_token}`;
    await Clipboard.setStringAsync(link);
    Alert.alert("Copied", "Portal link copied to clipboard");
  };

  const togglePlay = async () => {
    if (playerStatus.playing) {
      player.pause();
      return;
    }
    if (audioUrl) {
      player.play();
      return;
    }
    setLoadingTts(true);
    try {
      await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: false });
      const res = await api.ttsReport(id!);
      setAudioUrl(res.audio_data_url);
      // Autoplay after URL is set — expo-audio picks up the new source, then play
      setTimeout(() => {
        try { player.play(); } catch {}
      }, 200);
    } catch (e: any) {
      Alert.alert("Read aloud failed", e.message || "Could not generate audio");
    } finally {
      setLoadingTts(false);
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
        <View style={{ flexDirection: "row", gap: spacing.md }}>
          <Pressable onPress={onShare} testID="report-share">
            <Ionicons name="share-social" size={22} color={colors.brandPrimary} />
          </Pressable>
          <Pressable onPress={downloadWorkday} testID="workday-export">
            <Ionicons name="download" size={22} color={colors.brandPrimary} />
          </Pressable>
        </View>
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

        {(report.priority_level || (report.priority_flags && report.priority_flags.length > 0)) ? (
          <View style={styles.priorityBar} testID="priority-bar">
            {report.priority_level ? (
              <View
                testID="priority-level-chip"
                style={[
                  styles.priorityLevelChip,
                  { backgroundColor: priorityLevelColor(report.priority_level).bg },
                ]}
              >
                <Text
                  style={[
                    styles.priorityLevelText,
                    { color: priorityLevelColor(report.priority_level).text },
                  ]}
                >
                  {report.priority_level.toUpperCase()} PRIORITY
                </Text>
              </View>
            ) : null}
            <View style={styles.flagChipRow}>
              {(report.priority_flags || []).map((f: any) => (
                <View key={f.type} style={styles.flagChip} testID={`flag-chip-${f.type}`}>
                  <Text style={styles.flagChipText}>⚑ {f.type}</Text>
                </View>
              ))}
            </View>
          </View>
        ) : null}

        {report.email_sent_to?.length ? (
          <View style={styles.emailSentBox} testID="email-sent-box">
            <Ionicons name="mail" size={14} color={colors.success} />
            <Text style={styles.emailSentText}>Sent to: {report.email_sent_to.join(", ")}</Text>
          </View>
        ) : null}

        <View style={styles.card}>
          <View style={styles.summaryHeaderRow}>
            <Pressable
              testID="tts-play-button"
              onPress={togglePlay}
              disabled={loadingTts}
              style={({ pressed }) => [
                styles.playBtn,
                pressed && { opacity: 0.85 },
                loadingTts && { opacity: 0.7 },
              ]}
            >
              {loadingTts ? (
                <ActivityIndicator size="small" color={colors.onBrandPrimary} />
              ) : (
                <Ionicons
                  name={playerStatus.playing ? "pause" : "play"}
                  size={16}
                  color={colors.onBrandPrimary}
                />
              )}
              <Text style={styles.playBtnText}>
                {loadingTts
                  ? "Generating…"
                  : playerStatus.playing
                  ? "Pause"
                  : audioUrl
                  ? "Resume"
                  : "Read aloud"}
              </Text>
            </Pressable>
          </View>
          <StructuredSummary summary={report.ai_summary} />
        </View>

        {report.projects?.length ? (
          <MetaCard title={`Jobs on this report (${report.projects.length})`} testID="report-jobs">
            {report.projects.map((p: any, idx: number) => {
              const label =
                p.project_name ||
                p.customer_name ||
                p.project_code ||
                (p.address || "").slice(0, 60) ||
                `Project ${idx + 1}`;
              const jobResponses = responses.filter((r) => r.project_id === p.id);
              const isEditing = editingSummaryFor === p.id;
              return (
                <View key={p.id || idx} style={styles.jobCard} testID={`report-job-${idx}`}>
                  <View style={styles.jobCardHeader}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.jobTitle} numberOfLines={1}>{label}</Text>
                      {p.address ? (
                        <Text style={styles.jobAddr} numberOfLines={1}>{p.address}</Text>
                      ) : null}
                    </View>
                    {p.priority_flag ? (
                      <View style={styles.flagChip}>
                        <Ionicons name="flag" size={10} color={colors.error} />
                        <Text style={styles.flagChipText}>{p.priority_flag}</Text>
                      </View>
                    ) : null}
                  </View>

                  {isEditing ? (
                    <View>
                      <TextInput
                        testID={`job-summary-input-${idx}`}
                        value={summaryDraft}
                        onChangeText={setSummaryDraft}
                        placeholder="E.g. 3-coat interior repaint, kitchen + living, 3-day job"
                        placeholderTextColor={colors.muted}
                        multiline
                        style={styles.summaryInput}
                      />
                      <View style={styles.summaryBtnRow}>
                        <Pressable
                          testID={`job-summary-cancel-${idx}`}
                          onPress={() => { setEditingSummaryFor(null); setSummaryDraft(""); }}
                          style={styles.summarySecondary}
                        >
                          <Text style={styles.summarySecondaryText}>Cancel</Text>
                        </Pressable>
                        <Pressable
                          testID={`job-summary-save-${idx}`}
                          onPress={async () => {
                            setSavingSummary(true);
                            try {
                              await api.patchProjectSummary(id!, p.id, summaryDraft.trim() || null);
                              setEditingSummaryFor(null);
                              setSummaryDraft("");
                              await reload();
                            } catch {}
                            setSavingSummary(false);
                          }}
                          disabled={savingSummary}
                          style={[styles.summaryPrimary, savingSummary && { opacity: 0.7 }]}
                        >
                          {savingSummary ? (
                            <ActivityIndicator color={colors.onBrandPrimary} size="small" />
                          ) : (
                            <Text style={styles.summaryPrimaryText}>Save overview</Text>
                          )}
                        </Pressable>
                      </View>
                    </View>
                  ) : p.summary ? (
                    <Pressable
                      onPress={() => { setEditingSummaryFor(p.id); setSummaryDraft(p.summary || ""); }}
                      testID={`job-summary-edit-${idx}`}
                      style={styles.summaryCard}
                    >
                      <View style={styles.summaryCardHead}>
                        <Ionicons name="sparkles" size={11} color={colors.brandPrimary} />
                        <Text style={styles.summaryCardLabel}>Job overview</Text>
                        <Ionicons name="create-outline" size={13} color={colors.brandPrimary} />
                      </View>
                      <Text style={styles.summaryCardText}>{p.summary}</Text>
                    </Pressable>
                  ) : (
                    <Pressable
                      onPress={() => { setEditingSummaryFor(p.id); setSummaryDraft(""); }}
                      testID={`job-summary-add-${idx}`}
                      style={styles.addSummaryBtn}
                    >
                      <Ionicons name="add-circle-outline" size={14} color={colors.brandPrimary} />
                      <Text style={styles.addSummaryText}>Add a job overview</Text>
                    </Pressable>
                  )}

                  {p.notes ? (
                    <Text style={styles.jobNotes} numberOfLines={3}>{p.notes}</Text>
                  ) : null}

                  {jobResponses.length > 0 ? (
                    <View style={styles.repliesWrap}>
                      <Text style={styles.repliesTitle}>
                        {jobResponses.length} repl{jobResponses.length === 1 ? "y" : "ies"}
                      </Text>
                      {jobResponses.map((rp: any) => (
                        <View key={rp.id} style={styles.replyRow}>
                          <View style={[styles.replyDot, !rp.read_at && { backgroundColor: colors.error }]} />
                          <View style={{ flex: 1 }}>
                            <Text style={styles.replyFrom} numberOfLines={1}>
                              {rp.reporter_name || rp.reporter_email || "Anonymous"}
                            </Text>
                            <Text style={styles.replyBody} numberOfLines={2}>
                              {rp.message}
                            </Text>
                          </View>
                        </View>
                      ))}
                      <Pressable
                        onPress={() => router.push("/mail")}
                        testID={`job-open-mail-${idx}`}
                        style={styles.openMailLink}
                      >
                        <Ionicons name="mail" size={12} color={colors.brandPrimary} />
                        <Text style={styles.openMailText}>Open Mail</Text>
                      </Pressable>
                    </View>
                  ) : null}
                </View>
              );
            })}
          </MetaCard>
        ) : null}

        {report.weather && (
          <MetaCard title="Weather" testID="report-weather">
            <Text style={styles.metaText}>
              {Math.round(report.weather.temperature_f)}°F · wind{" "}
              {Math.round(report.weather.wind_mph || 0)} mph · precip{" "}
              {(report.weather.precipitation || 0).toFixed(2)}"
            </Text>
          </MetaCard>
        )}

        {report.projects?.length && report.projects.some((p: any) => p.weather) ? (
          <MetaCard title="Weather by site" testID="report-per-site-weather">
            {report.projects.map((p: any, idx: number) => (
              p.weather ? (
                <View key={p.id || idx} style={styles.mini} testID={`report-site-weather-${idx}`}>
                  <Text style={styles.miniTitle} numberOfLines={1}>
                    {p.customer_name || p.address || `Project ${idx + 1}`}
                  </Text>
                  {p.address ? (
                    <Text style={styles.miniSub} numberOfLines={1}>{p.address}</Text>
                  ) : null}
                  <Text style={styles.miniNotes}>
                    {p.weather.conditions} · {Math.round(p.weather.temperature_f)}°F · wind{" "}
                    {Math.round(p.weather.wind_mph || 0)} mph · precip{" "}
                    {(p.weather.precipitation || 0).toFixed(2)}"
                  </Text>
                </View>
              ) : null
            ))}
          </MetaCard>
        ) : null}

        {report.visits?.length ? (
          <MetaCard title={`Visits (${report.visits.length})`} testID="report-visits">
            {report.visits.map((v: any) => (
              <View key={v.id} style={styles.mini}>
                <Text style={styles.miniTitle}>{v.customer_name || "Job Site"}</Text>
                <Text style={styles.miniSub}>
                  {v.address || `${v.latitude?.toFixed?.(4)}, ${v.longitude?.toFixed?.(4)}`}
                </Text>
                {v.notes ? <Text style={styles.miniNotes}>{v.notes}</Text> : null}
                {v.photos?.length ? (
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: spacing.sm }}>
                    <View style={{ flexDirection: "row", gap: 6 }}>
                      {v.photos.map((p: string, i: number) => (
                        <VisitPhotoTile key={p + i} path={p} testID={`report-visit-photo-${v.id}-${i}`} />
                      ))}
                    </View>
                  </ScrollView>
                ) : null}
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

        {/* Portal Link */}
        <MetaCard title="Customer Portal Link" testID="report-portal">
          {report.public_token ? (
            <View>
              <Text style={styles.miniSub}>
                Anyone with this link can view the report summary and signature (no login needed).
              </Text>
              <View style={styles.portalRow}>
                <Text style={styles.portalLink} numberOfLines={1}>
                  {process.env.EXPO_PUBLIC_BACKEND_URL}/api/public/reports/{report.public_token}
                </Text>
              </View>
              <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm }}>
                <Pressable testID="portal-copy" onPress={copyPortalLink} style={[styles.smallBtn, { backgroundColor: colors.brandPrimary, flex: 1 }]}>
                  <Text style={{ color: colors.onBrandPrimary, fontWeight: "700" }}>Copy Link</Text>
                </Pressable>
                <Pressable testID="portal-revoke" onPress={revokePortalLink} style={[styles.smallBtn, { backgroundColor: colors.surfaceTertiary, flex: 1 }]}>
                  <Text style={{ color: colors.error, fontWeight: "700" }}>Revoke</Text>
                </Pressable>
              </View>
            </View>
          ) : (
            <Pressable testID="portal-generate" onPress={generatePortalLink} style={styles.signCTA}>
              <Ionicons name="link" size={16} color={colors.onBrandPrimary} />
              <Text style={{ color: colors.onBrandPrimary, fontWeight: "700" }}>Generate Share Link</Text>
            </Pressable>
          )}
        </MetaCard>

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

function VisitPhotoTile({ path, testID }: { path: string; testID: string }) {
  const [uri, setUri] = useState<string | null>(null);
  useEffect(() => {
    authedPhotoUrl(path).then(setUri);
  }, [path]);
  return (
    <Image
      testID={testID}
      source={uri ? { uri } : undefined}
      style={{ width: 100, height: 100, borderRadius: 8, backgroundColor: colors.surfaceTertiary }}
      contentFit="cover"
    />
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
  priorityBar: {
    marginTop: spacing.md,
    gap: spacing.xs,
  },
  priorityLevelChip: {
    alignSelf: "flex-start",
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: radius.pill,
  },
  priorityLevelText: { fontSize: 11, fontWeight: "800", letterSpacing: 0.5 },
  flagChipRow: { flexDirection: "row", flexWrap: "wrap", gap: 4 },
  flagChip: {
    backgroundColor: colors.brandTertiary,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: radius.pill,
  },
  flagChipText: { color: colors.onBrandTertiary, fontSize: 11, fontWeight: "700" },
  summaryHeaderRow: { flexDirection: "row", justifyContent: "flex-end", marginBottom: spacing.sm },
  playBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: radius.pill,
  },
  playBtnText: { color: colors.onBrandPrimary, fontWeight: "700", fontSize: 12 },
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
  portalRow: {
    backgroundColor: colors.surfaceTertiary,
    padding: spacing.sm,
    borderRadius: radius.md,
    marginTop: spacing.sm,
  },
  portalLink: { color: colors.onSurface, fontSize: 11, fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace" },
  jobCard: {
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  jobCardHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    marginBottom: 6,
  },
  jobTitle: { color: colors.onSurface, fontWeight: "700", fontSize: 14 },
  jobAddr: { color: colors.muted, fontSize: 11, marginTop: 1 },
  flagChip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 3,
    backgroundColor: "#FEE2E2",
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: radius.pill,
  },
  flagChipText: { color: colors.error, fontSize: 10, fontWeight: "700" },
  summaryCard: {
    marginTop: 4,
    padding: 10,
    backgroundColor: "#FFF7ED",
    borderLeftWidth: 3,
    borderLeftColor: colors.brandPrimary,
    borderRadius: 6,
  },
  summaryCardHead: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    marginBottom: 4,
  },
  summaryCardLabel: {
    color: colors.brandPrimary,
    fontSize: 10,
    fontWeight: "800",
    textTransform: "uppercase",
    letterSpacing: 0.5,
    flex: 1,
  },
  summaryCardText: { color: colors.onSurface, fontSize: 13, lineHeight: 19 },
  addSummaryBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingVertical: 6,
    paddingHorizontal: 10,
    backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.pill,
    alignSelf: "flex-start",
    marginTop: 4,
  },
  addSummaryText: { color: colors.brandPrimary, fontWeight: "700", fontSize: 12 },
  summaryInput: {
    backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.md,
    padding: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border,
    minHeight: 70,
    textAlignVertical: "top",
    color: colors.onSurface,
    fontSize: 13,
    marginTop: 4,
  },
  summaryBtnRow: {
    flexDirection: "row",
    justifyContent: "flex-end",
    gap: 8,
    marginTop: spacing.sm,
  },
  summarySecondary: {
    paddingHorizontal: spacing.md,
    paddingVertical: 7,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
  },
  summarySecondaryText: { color: colors.onSurface, fontWeight: "700", fontSize: 12 },
  summaryPrimary: {
    paddingHorizontal: spacing.md,
    paddingVertical: 7,
    backgroundColor: colors.brandPrimary,
    borderRadius: radius.pill,
  },
  summaryPrimaryText: { color: colors.onBrandPrimary, fontWeight: "700", fontSize: 12 },
  jobNotes: {
    color: colors.onSurfaceTertiary,
    fontSize: 12,
    marginTop: 8,
    lineHeight: 17,
  },
  repliesWrap: {
    marginTop: spacing.sm,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.divider,
  },
  repliesTitle: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: "800",
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginBottom: 6,
  },
  replyRow: {
    flexDirection: "row",
    gap: 8,
    paddingVertical: 4,
    alignItems: "flex-start",
  },
  replyDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.borderStrong,
    marginTop: 6,
  },
  replyFrom: { color: colors.onSurface, fontWeight: "700", fontSize: 12 },
  replyBody: { color: colors.onSurfaceTertiary, fontSize: 12, marginTop: 1 },
  openMailLink: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    marginTop: 6,
    alignSelf: "flex-start",
  },
  openMailText: { color: colors.brandPrimary, fontWeight: "700", fontSize: 11 },
});
