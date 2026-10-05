import { useState, useEffect, useRef, useCallback } from "react";
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
import { PriorityPicker, PriorityFlagEntry } from "@/src/components/PriorityPicker";
import { ProjectsSection, ProjectEntry } from "@/src/components/ProjectsSection";
import { flagRequiresReason } from "@/src/priority";
import { colors, spacing, radius } from "@/src/theme";

type DraftSaveStatus = "idle" | "saving" | "saved" | "error";

const AUTOSAVE_DEBOUNCE_MS = 900;

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
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [transcribing, setTranscribing] = useState(false);
  const [priorityLevel, setPriorityLevel] = useState<string | null>(null);
  const [priorityFlags, setPriorityFlags] = useState<PriorityFlagEntry[]>([]);
  const [projects, setProjects] = useState<ProjectEntry[]>([]);
  const [loadingDraft, setLoadingDraft] = useState(true);
  const [draftStatus, setDraftStatus] = useState<DraftSaveStatus>("idle");
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const [draftLoaded, setDraftLoaded] = useState(false);

  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inFlightRef = useRef(false);
  const pendingRef = useRef(false);
  const draftLoadedRef = useRef(false);

  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const recorderState = useAudioRecorderState(recorder);

  // Load today's draft (if any), else derive projects from today's visits as a seed
  useEffect(() => {
    (async () => {
      try {
        const draft = await api.getDraftToday();
        if (draft) {
          setProjectName(draft.project_name || "");
          setProjectCode(draft.project_code || "");
          setHighlights(draft.highlights || "");
          setDelays(draft.delays || "");
          setChangeOrders(draft.change_orders || "");
          setMaterialNotes(draft.material_notes || "");
          setIncludeWeather(draft.include_weather !== false);
          setIncludeVisits(draft.include_visits !== false);
          setIncludeBreaks(draft.include_breaks !== false);
          setIncludeSms(draft.include_sms !== false);
          setPriorityLevel(draft.priority_level ?? null);
          setPriorityFlags(
            Array.isArray(draft.priority_flags)
              ? draft.priority_flags.map((f: any) => ({ type: f.type, reason: f.reason ?? "" }))
              : [],
          );
          setProjects(Array.isArray(draft.projects) ? draft.projects : []);
          setEmailsText(Array.isArray(draft.recipient_emails) ? draft.recipient_emails.join(", ") : "");
          if (draft.updated_at) setLastSavedAt(new Date(draft.updated_at));
        } else {
          // No draft yet — seed projects from today's visits so the user doesn't start empty
          try {
            const visits = await api.visitsToday();
            if (Array.isArray(visits) && visits.length > 0) {
              const byPid = new Map<string, ProjectEntry>();
              const derived: ProjectEntry[] = [];
              for (const v of visits) {
                const pid: string | null = v.project_id || null;
                if (pid && byPid.has(pid)) {
                  const existing = byPid.get(pid)!;
                  existing.visit_ids = [...(existing.visit_ids || []), v.id];
                  existing.photos = [...(existing.photos || []), ...(v.photos || [])];
                  if (v.notes) {
                    existing.notes = existing.notes ? `${existing.notes}\n${v.notes}` : v.notes;
                  }
                  continue;
                }
                const entry: ProjectEntry = {
                  id: pid || `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
                  project_code: v.project_code || "",
                  project_name: "",
                  customer_name: v.customer_name || "",
                  address: v.address || "",
                  latitude: v.latitude,
                  longitude: v.longitude,
                  notes: v.notes || "",
                  materials_used: "",
                  start_time: v.timestamp
                    ? new Date(v.timestamp).toLocaleTimeString([], {
                        hour: "numeric",
                        minute: "2-digit",
                      })
                    : "",
                  end_time: v.ended_at
                    ? new Date(v.ended_at).toLocaleTimeString([], {
                        hour: "numeric",
                        minute: "2-digit",
                      })
                    : "",
                  priority_flag: null,
                  touch_up: false,
                  photos: v.photos || [],
                  visit_ids: [v.id],
                };
                if (pid) byPid.set(pid, entry);
                derived.push(entry);
              }
              setProjects(derived);
            }
          } catch {}
        }
      } catch {
        // ignore – allow fresh start
      } finally {
        setLoadingDraft(false);
        setDraftLoaded(true);
        draftLoadedRef.current = true;
      }
    })();
  }, []);

  const buildDraftPayload = useCallback(() => {
    const recipient_emails = emailsText
      .split(",")
      .map((e) => e.trim())
      .filter((e) => e.length > 0);
    return {
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
      priority_level: priorityLevel,
      priority_flags: priorityFlags.map((f) => ({ type: f.type, reason: f.reason || null })),
      projects: projects.map((p) => ({
        id: p.id,
        project_code: p.project_code || null,
        project_name: p.project_name || null,
        customer_name: p.customer_name || null,
        address: p.address || null,
        latitude: p.latitude ?? null,
        longitude: p.longitude ?? null,
        notes: p.notes || null,
        materials_used: p.materials_used || null,
        start_time: p.start_time || null,
        end_time: p.end_time || null,
        priority_flag: p.priority_flag || null,
        touch_up: !!p.touch_up,
        photos: p.photos || [],
        visit_ids: p.visit_ids || [],
        summary: p.summary || null,
      })),
    };
  }, [
    project_name,
    project_code,
    highlights,
    delays,
    changeOrders,
    materialNotes,
    includeWeather,
    includeVisits,
    includeBreaks,
    includeSms,
    emailsText,
    priorityLevel,
    priorityFlags,
    projects,
  ]);

  const flushDraft = useCallback(async () => {
    if (inFlightRef.current) {
      pendingRef.current = true;
      return;
    }
    inFlightRef.current = true;
    setDraftStatus("saving");
    try {
      const payload = buildDraftPayload();
      const saved = await api.saveDraft(payload);
      if (saved?.updated_at) setLastSavedAt(new Date(saved.updated_at));
      else setLastSavedAt(new Date());
      setDraftStatus("saved");
    } catch {
      setDraftStatus("error");
    } finally {
      inFlightRef.current = false;
      if (pendingRef.current) {
        pendingRef.current = false;
        // one more pass with the latest state
        setTimeout(() => flushDraft(), 50);
      }
    }
  }, [buildDraftPayload]);

  // Debounced auto-save whenever any field changes (after initial draft load)
  useEffect(() => {
    if (!draftLoadedRef.current) return;
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      flushDraft();
    }, AUTOSAVE_DEBOUNCE_MS);
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, [
    draftLoaded,
    project_name,
    project_code,
    highlights,
    delays,
    changeOrders,
    materialNotes,
    includeWeather,
    includeVisits,
    includeBreaks,
    includeSms,
    emailsText,
    priorityLevel,
    priorityFlags,
    projects,
    flushDraft,
  ]);

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

  const submit = async () => {
    setError(null);
    const missingReason = priorityFlags.find(
      (f) => flagRequiresReason(f.type) && !(f.reason || "").trim(),
    );
    if (missingReason) {
      setError(`Please add a reason for "${missingReason.type}".`);
      return;
    }
    setSubmitting(true);
    try {
      // Ensure latest edits are saved before submission
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
        saveTimerRef.current = null;
      }
      await flushDraft();
      // Wait for any in-flight save to finish
      await new Promise<void>((resolve) => {
        const check = () => {
          if (!inFlightRef.current) resolve();
          else setTimeout(check, 50);
        };
        check();
      });
      const r = await api.submitDraft();
      router.replace(`/report/${r.id}`);
    } catch (e: any) {
      setError(e.message || "Failed to submit report");
    } finally {
      setSubmitting(false);
    }
  };

  const discard = () => {
    Alert.alert(
      "Discard today's draft?",
      "This will clear all unsaved entries for today. This can't be undone.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Discard",
          style: "destructive",
          onPress: async () => {
            try {
              if (saveTimerRef.current) {
                clearTimeout(saveTimerRef.current);
                saveTimerRef.current = null;
              }
              await api.discardDraft();
            } catch {}
            router.back();
          },
        },
      ],
    );
  };

  const draftIndicator = (() => {
    if (loadingDraft) return { text: "Loading draft…", icon: "cloud-download" as const };
    if (draftStatus === "saving") return { text: "Saving draft…", icon: "cloud-upload" as const };
    if (draftStatus === "error") return { text: "Draft save failed", icon: "warning" as const };
    if (lastSavedAt)
      return {
        text: `Draft saved · ${lastSavedAt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`,
        icon: "checkmark-circle" as const,
      };
    return { text: "Draft auto-saves as you type", icon: "sync" as const };
  })();

  const indicatorColor =
    draftStatus === "error"
      ? colors.error
      : draftStatus === "saving"
      ? colors.muted
      : lastSavedAt
      ? colors.success
      : colors.muted;

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.surface }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} testID="report-close">
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Today's Report</Text>
        <Pressable onPress={discard} testID="draft-discard" hitSlop={10}>
          <Ionicons name="trash-outline" size={22} color={colors.muted} />
        </Pressable>
      </View>

      <View style={styles.statusBar} testID="draft-status">
        <Ionicons name={draftIndicator.icon} size={14} color={indicatorColor} />
        <Text style={[styles.statusText, { color: indicatorColor }]}>{draftIndicator.text}</Text>
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

        <ProjectsSection projects={projects} onChange={setProjects} />

        <View style={styles.togglesCard}>
          <Toggle label="Include today's visits" value={includeVisits} onChange={setIncludeVisits} testID="toggle-visits" />
          <Toggle label="Include breaks" value={includeBreaks} onChange={setIncludeBreaks} testID="toggle-breaks" />
          <Toggle label="Include communications log" value={includeSms} onChange={setIncludeSms} testID="toggle-sms" />
          <Toggle label="Include weather" value={includeWeather} onChange={setIncludeWeather} testID="toggle-weather" />
        </View>

        <PriorityPicker
          level={priorityLevel}
          onLevelChange={setPriorityLevel}
          flags={priorityFlags}
          onFlagsChange={setPriorityFlags}
        />

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
          onPress={submit}
          disabled={submitting}
          style={({ pressed }) => [
            styles.primaryBtn,
            pressed && { opacity: 0.85 },
            submitting && { opacity: 0.7 },
          ]}
        >
          {submitting ? (
            <>
              <ActivityIndicator color={colors.onBrandPrimary} />
              <Text style={[styles.primaryBtnText, { marginLeft: spacing.sm }]}>
                Generating AI summary…
              </Text>
            </>
          ) : (
            <>
              <Ionicons name="send" size={18} color={colors.onBrandPrimary} />
              <Text style={[styles.primaryBtnText, { marginLeft: spacing.sm }]}>
                Submit Report
              </Text>
            </>
          )}
        </Pressable>

        <Text style={styles.helpText}>
          Add entries throughout the day — everything is saved as a draft until you submit.
        </Text>
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
  statusBar: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: spacing.lg,
    paddingVertical: 6,
    backgroundColor: colors.surfaceSecondary,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  statusText: { fontSize: 11, fontWeight: "600" },
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
  helpText: {
    marginTop: spacing.md,
    color: colors.muted,
    fontSize: 12,
    textAlign: "center",
  },
});
