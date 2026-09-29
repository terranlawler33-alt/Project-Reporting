import { useState, useRef } from "react";
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
  Switch,
  Alert,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import {
  useAudioRecorder,
  useAudioRecorderState,
  RecordingPresets,
  setAudioModeAsync,
  AudioModule,
} from "expo-audio";
import { api } from "@/src/api";
import { transcribeAudio } from "@/src/voice";
import { RecipientGroupPicker } from "@/src/components/RecipientGroupPicker";
import { colors, spacing, radius } from "@/src/theme";

export default function NewReport() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [project_name, setProjectName] = useState("");
  const [project_code, setProjectCode] = useState("");
  const [highlights, setHighlights] = useState("");
  const [delays, setDelays] = useState("");
  const [changeOrders, setChangeOrders] = useState("");
  const [materialNotes, setMaterialNotes] = useState("");
  const [emailsText, setEmailsText] = useState("");
  const [includeWeather, setIncludeWeather] = useState(true);
  const [includeVisits, setIncludeVisits] = useState(true);
  const [includeBreaks, setIncludeBreaks] = useState(true);
  const [includeSms, setIncludeSms] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [transcribing, setTranscribing] = useState(false);

  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const recorderState = useAudioRecorderState(recorder);

  const toggleRecord = async () => {
    if (recorderState.isRecording) {
      try {
        await recorder.stop();
        const uri = recorder.uri;
        if (!uri) return;
        setTranscribing(true);
        try {
          const text = await transcribeAudio(uri);
          if (text) {
            setHighlights((prev) => (prev ? `${prev}\n${text}` : text));
          } else {
            setError("No speech detected. Try again.");
          }
        } catch (e: any) {
          setError(e.message || "Transcription failed");
        } finally {
          setTranscribing(false);
        }
      } catch (e: any) {
        setError(e.message || "Recording failed");
      }
    } else {
      try {
        const perm = await AudioModule.requestRecordingPermissionsAsync();
        if (!perm.granted) {
          Alert.alert("Microphone permission required", "Enable mic access in settings to dictate notes.");
          return;
        }
        await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true });
        await recorder.prepareToRecordAsync();
        recorder.record();
      } catch (e: any) {
        setError(e.message || "Failed to start recording");
      }
    }
  };

  const generate = async () => {
    setError(null);
    setSaving(true);
    try {
      const recipient_emails = emailsText
        .split(",")
        .map((e) => e.trim())
        .filter((e) => e.length > 0);
      const r = await api.createReport({
        project_name: project_name || null,
        project_code: project_code || null,
        highlights,
        delays,
        change_orders: changeOrders,
        material_notes: materialNotes,
        include_weather: includeWeather,
        include_visits: includeVisits,
        include_breaks: includeBreaks,
        include_sms: includeSms,
        recipient_emails,
      });
      router.replace(`/report/${r.id}`);
    } catch (e: any) {
      setError(e.message || "Failed to generate report");
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
        <Pressable onPress={() => router.back()} testID="report-close">
          <Ionicons name="close" size={26} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Compose Report</Text>
        <View style={{ width: 26 }} />
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 60 }}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={styles.label}>Project name</Text>
        <TextInput
          testID="report-project-name"
          value={project_name}
          onChangeText={setProjectName}
          placeholder="e.g. Willow Ridge Ext."
          placeholderTextColor={colors.muted}
          style={styles.input}
        />
        <Text style={styles.label}>Project code</Text>
        <TextInput
          testID="report-project-code"
          value={project_code}
          onChangeText={setProjectCode}
          placeholder="e.g. P-1042"
          placeholderTextColor={colors.muted}
          style={styles.input}
        />
        <View style={styles.labelRow}>
          <Text style={styles.label}>Highlights (tasks completed)</Text>
          <Pressable
            testID="voice-mic-button"
            onPress={toggleRecord}
            disabled={transcribing}
            style={[
              styles.micBtn,
              recorderState.isRecording && styles.micBtnRecording,
              transcribing && { opacity: 0.7 },
            ]}
          >
            {transcribing ? (
              <ActivityIndicator size="small" color={colors.onBrandPrimary} />
            ) : (
              <Ionicons
                name={recorderState.isRecording ? "stop" : "mic"}
                size={16}
                color={colors.onBrandPrimary}
              />
            )}
            <Text style={styles.micBtnText}>
              {transcribing ? "Transcribing…" : recorderState.isRecording ? "Stop" : "Dictate"}
            </Text>
          </Pressable>
        </View>
        <TextInput
          testID="report-highlights"
          value={highlights}
          onChangeText={setHighlights}
          placeholder="Interior prep 60%, primed north wall, crew of 4 on site"
          placeholderTextColor={colors.muted}
          style={[styles.input, styles.multi]}
          multiline
        />
        <Text style={styles.label}>Delays</Text>
        <TextInput
          testID="report-delays"
          value={delays}
          onChangeText={setDelays}
          placeholder="Weather, traffic, subs, materials..."
          placeholderTextColor={colors.muted}
          style={[styles.input, styles.multi]}
          multiline
        />
        <Text style={styles.label}>Change orders</Text>
        <TextInput
          testID="report-change-orders"
          value={changeOrders}
          onChangeText={setChangeOrders}
          placeholder="Any customer-approved changes"
          placeholderTextColor={colors.muted}
          style={[styles.input, styles.multi]}
          multiline
        />
        <Text style={styles.label}>Material notes</Text>
        <TextInput
          testID="report-material-notes"
          value={materialNotes}
          onChangeText={setMaterialNotes}
          placeholder="Deliveries, shortages, damage"
          placeholderTextColor={colors.muted}
          style={[styles.input, styles.multi]}
          multiline
        />

        <View style={styles.togglesCard}>
          <Toggle label="Include today's visits" value={includeVisits} onChange={setIncludeVisits} testID="toggle-visits" />
          <Toggle label="Include breaks" value={includeBreaks} onChange={setIncludeBreaks} testID="toggle-breaks" />
          <Toggle label="Include communications log" value={includeSms} onChange={setIncludeSms} testID="toggle-sms" />
          <Toggle label="Include weather" value={includeWeather} onChange={setIncludeWeather} testID="toggle-weather" />
        </View>

        <Text style={styles.label}>Email to management (comma-separated)</Text>
        <RecipientGroupPicker
          testID="new-report-group-picker"
          onPick={(emails) => {
            const existing = emailsText
              .split(",")
              .map((e) => e.trim())
              .filter((e) => e.length > 0);
            const merged = Array.from(new Set([...existing, ...emails]));
            setEmailsText(merged.join(", "));
          }}
        />
        <TextInput
          testID="report-emails"
          value={emailsText}
          onChangeText={setEmailsText}
          placeholder="owner@company.com, ops@company.com"
          placeholderTextColor={colors.muted}
          autoCapitalize="none"
          keyboardType="email-address"
          style={styles.input}
        />

        {error ? (
          <Text style={styles.error} testID="report-error">
            {error}
          </Text>
        ) : null}

        <Pressable
          testID="report-generate"
          onPress={generate}
          disabled={saving}
          style={({ pressed }) => [
            styles.primaryBtn,
            pressed && { opacity: 0.85 },
            saving && { opacity: 0.7 },
          ]}
        >
          {saving ? (
            <>
              <ActivityIndicator color={colors.onBrandPrimary} />
              <Text style={[styles.primaryBtnText, { marginLeft: spacing.sm }]}>
                Generating AI summary…
              </Text>
            </>
          ) : (
            <>
              <Ionicons name="sparkles" size={18} color={colors.onBrandPrimary} />
              <Text style={[styles.primaryBtnText, { marginLeft: spacing.sm }]}>
                Generate & Send
              </Text>
            </>
          )}
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function Toggle({
  label,
  value,
  onChange,
  testID,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
  testID: string;
}) {
  return (
    <View style={styles.toggleRow}>
      <Text style={styles.toggleLabel}>{label}</Text>
      <Switch
        testID={testID}
        value={value}
        onValueChange={onChange}
        trackColor={{ true: colors.brandPrimary, false: colors.borderStrong }}
      />
    </View>
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
  label: {
    color: colors.onSurfaceTertiary,
    fontSize: 13,
    fontWeight: "700",
    marginTop: spacing.md,
    marginBottom: spacing.xs,
  },
  labelRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: spacing.md,
    marginBottom: spacing.xs,
  },
  micBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.sm,
    paddingVertical: 6,
    borderRadius: radius.pill,
  },
  micBtnRecording: { backgroundColor: colors.error },
  micBtnText: { color: colors.onBrandPrimary, fontWeight: "700", fontSize: 12 },
  input: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    padding: spacing.md,
    color: colors.onSurface,
    borderWidth: 1,
    borderColor: colors.border,
    fontSize: 14,
  },
  multi: { minHeight: 70, textAlignVertical: "top" },
  togglesCard: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.sm,
    marginTop: spacing.lg,
  },
  toggleRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    padding: spacing.sm,
  },
  toggleLabel: { color: colors.onSurface, fontSize: 14, fontWeight: "600" },
  error: { color: colors.error, marginTop: spacing.md, fontSize: 13 },
  primaryBtn: {
    marginTop: spacing.xl,
    backgroundColor: colors.brandPrimary,
    padding: spacing.md + 2,
    borderRadius: radius.md,
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "center",
  },
  primaryBtnText: { color: colors.onBrandPrimary, fontWeight: "700", fontSize: 15 },
});
