import { useState } from "react";
import {
  View,
  Text,
  TextInput,
  Pressable,
  StyleSheet,
  Switch,
  ScrollView,
  ActivityIndicator,
  Alert,
} from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import {
  useAudioRecorder,
  useAudioRecorderState,
  RecordingPresets,
  setAudioModeAsync,
  AudioModule,
} from "expo-audio";
import { colors, spacing, radius } from "@/src/theme";
import { PRIORITY_FLAGS } from "@/src/priority";
import { transcribeAudio } from "@/src/voice";
import { api } from "@/src/api";

export type ProjectEntry = {
  id: string;
  project_code?: string | null;
  project_name?: string | null;
  customer_name?: string | null;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  notes?: string | null;
  materials_used?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  priority_flag?: string | null;
  touch_up?: boolean;
  photos?: string[];
  visit_ids?: string[];
};

function newProject(): ProjectEntry {
  return {
    id: Math.random().toString(36).slice(2) + Date.now().toString(36),
    project_code: "",
    project_name: "",
    customer_name: "",
    address: "",
    latitude: null,
    longitude: null,
    notes: "",
    materials_used: "",
    start_time: "",
    end_time: "",
    priority_flag: null,
    touch_up: false,
    photos: [],
    visit_ids: [],
  };
}

type Props = {
  projects: ProjectEntry[];
  onChange: (next: ProjectEntry[]) => void;
};

export function ProjectsSection({ projects, onChange }: Props) {
  const [openFlagPickerFor, setOpenFlagPickerFor] = useState<string | null>(null);
  const [dictatingFor, setDictatingFor] = useState<string | null>(null);
  const [parsingFor, setParsingFor] = useState<string | null>(null);
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const recorderState = useAudioRecorderState(recorder);

  const update = (id: string, patch: Partial<ProjectEntry>) => {
    onChange(projects.map((p) => (p.id === id ? { ...p, ...patch } : p)));
  };
  const remove = (id: string) => onChange(projects.filter((p) => p.id !== id));
  const add = () => onChange([...projects, newProject()]);

  // Merge parsed fields into a project — only overwrite EMPTY fields, and always
  // append parsed notes rather than clobber existing ones.
  const mergeParsed = (id: string, parsed: any) => {
    const current = projects.find((p) => p.id === id);
    if (!current) return;
    const patch: Partial<ProjectEntry> = {};
    const isEmpty = (v: any) => v == null || String(v).trim() === "";
    if (parsed.customer_name && isEmpty(current.customer_name)) patch.customer_name = parsed.customer_name;
    if (parsed.address && isEmpty(current.address)) patch.address = parsed.address;
    if (parsed.project_code && isEmpty(current.project_code)) patch.project_code = parsed.project_code;
    if (parsed.project_name && isEmpty(current.project_name)) patch.project_name = parsed.project_name;
    if (parsed.materials_used && isEmpty(current.materials_used)) patch.materials_used = parsed.materials_used;
    if (parsed.start_time && isEmpty(current.start_time)) patch.start_time = parsed.start_time;
    if (parsed.end_time && isEmpty(current.end_time)) patch.end_time = parsed.end_time;
    if (parsed.priority_flag && !current.priority_flag) patch.priority_flag = parsed.priority_flag;
    if (parsed.touch_up === true && !current.touch_up) patch.touch_up = true;
    if (parsed.notes) {
      patch.notes = current.notes
        ? `${current.notes}\n${parsed.notes}`
        : parsed.notes;
    }
    update(id, patch);
  };

  const startDictate = async (projectId: string) => {
    if (recorderState.isRecording || dictatingFor || parsingFor) return;
    try {
      const perm = await AudioModule.requestRecordingPermissionsAsync();
      if (!perm.granted) {
        Alert.alert("Microphone permission needed", "Enable mic access to dictate this project.");
        return;
      }
      await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
      setDictatingFor(projectId);
    } catch (e: any) {
      Alert.alert("Recording failed", e?.message || "Could not start recording");
    }
  };

  const stopDictate = async () => {
    const projectId = dictatingFor;
    setDictatingFor(null);
    if (!projectId) return;
    try {
      await recorder.stop();
      const uri = recorder.uri;
      if (!uri) return;
      setParsingFor(projectId);
      try {
        const text = await transcribeAudio(uri);
        if (!text) {
          Alert.alert("No speech detected", "Try again in a quieter spot.");
          return;
        }
        const parsed = await api.parseProject(text);
        mergeParsed(projectId, parsed);
      } catch (e: any) {
        Alert.alert("Could not parse", e?.message || "Please fill fields manually.");
      } finally {
        setParsingFor(null);
      }
    } catch (e: any) {
      setParsingFor(null);
      Alert.alert("Recording failed", e?.message || "Please try again.");
    }
  };

  const toggleMic = (projectId: string) => {
    if (dictatingFor === projectId) {
      void stopDictate();
    } else {
      void startDictate(projectId);
    }
  };

  return (
    <View testID="projects-section" style={styles.wrap}>
      <View style={styles.sectionHeaderRow}>
        <View style={styles.sectionTitleWrap}>
          <Ionicons name="briefcase" size={16} color={colors.brandPrimary} />
          <Text style={styles.sectionTitle}>Projects</Text>
        </View>
        <Text style={styles.count}>{projects.length}</Text>
      </View>
      <Text style={styles.hint}>
        Add each job site worked on today. Pin drops from the map get attached here automatically.
      </Text>

      {projects.map((p, idx) => {
        const isRecordingThis = dictatingFor === p.id;
        const isParsingThis = parsingFor === p.id;
        const anotherBusy =
          (!!dictatingFor && dictatingFor !== p.id) ||
          (!!parsingFor && parsingFor !== p.id);
        return (
        <View key={p.id} style={styles.card} testID={`project-card-${idx}`}>
          <View style={styles.cardHeader}>
            <Text style={styles.cardTitle}>Project {idx + 1}</Text>
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
              <Pressable
                testID={`project-mic-${idx}`}
                onPress={() => toggleMic(p.id)}
                disabled={anotherBusy || isParsingThis}
                hitSlop={8}
                style={[
                  styles.micBtn,
                  isRecordingThis && styles.micBtnRecording,
                  (anotherBusy || isParsingThis) && { opacity: 0.5 },
                ]}
              >
                {isParsingThis ? (
                  <ActivityIndicator size="small" color={colors.onBrandPrimary} />
                ) : (
                  <Ionicons
                    name={isRecordingThis ? "stop" : "mic"}
                    size={14}
                    color={colors.onBrandPrimary}
                  />
                )}
                <Text style={styles.micBtnText}>
                  {isParsingThis ? "Parsing…" : isRecordingThis ? "Stop" : "Dictate"}
                </Text>
              </Pressable>
              <Pressable
                testID={`project-remove-${idx}`}
                onPress={() => remove(p.id)}
                hitSlop={10}
              >
                <Ionicons name="trash-outline" size={18} color={colors.error} />
              </Pressable>
            </View>
          </View>

          <Text style={styles.label}>Customer name</Text>
          <TextInput
            testID={`project-customer-${idx}`}
            value={p.customer_name || ""}
            onChangeText={(t) => update(p.id, { customer_name: t })}
            placeholder="e.g. John Doe"
            placeholderTextColor={colors.muted}
            style={styles.input}
          />

          <Text style={styles.label}>Address</Text>
          <TextInput
            testID={`project-address-${idx}`}
            value={p.address || ""}
            onChangeText={(t) => update(p.id, { address: t })}
            placeholder="Street address (matches pin drop location)"
            placeholderTextColor={colors.muted}
            style={styles.input}
          />
          {p.latitude != null && p.longitude != null ? (
            <Text style={styles.coordText}>
              📍 {p.latitude.toFixed(5)}, {p.longitude.toFixed(5)}
            </Text>
          ) : null}

          <View style={styles.row2}>
            <View style={{ flex: 1 }}>
              <Text style={styles.label}>Project code</Text>
              <TextInput
                testID={`project-code-${idx}`}
                value={p.project_code || ""}
                onChangeText={(t) => update(p.id, { project_code: t })}
                placeholder="P-1042"
                placeholderTextColor={colors.muted}
                style={styles.input}
              />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.label}>Project name</Text>
              <TextInput
                testID={`project-name-${idx}`}
                value={p.project_name || ""}
                onChangeText={(t) => update(p.id, { project_name: t })}
                placeholder="Willow Ridge Ext."
                placeholderTextColor={colors.muted}
                style={styles.input}
              />
            </View>
          </View>

          <View style={styles.row2}>
            <View style={{ flex: 1 }}>
              <Text style={styles.label}>Start time</Text>
              <TextInput
                testID={`project-start-${idx}`}
                value={p.start_time || ""}
                onChangeText={(t) => update(p.id, { start_time: t })}
                placeholder="8:00 AM"
                placeholderTextColor={colors.muted}
                style={styles.input}
              />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.label}>End time</Text>
              <TextInput
                testID={`project-end-${idx}`}
                value={p.end_time || ""}
                onChangeText={(t) => update(p.id, { end_time: t })}
                placeholder="3:30 PM"
                placeholderTextColor={colors.muted}
                style={styles.input}
              />
            </View>
          </View>

          <Text style={styles.label}>Work notes</Text>
          <TextInput
            testID={`project-notes-${idx}`}
            value={p.notes || ""}
            onChangeText={(t) => update(p.id, { notes: t })}
            placeholder="Tasks done, crew, issues on this site"
            placeholderTextColor={colors.muted}
            style={[styles.input, styles.multi]}
            multiline
          />

          <Text style={styles.label}>Materials used</Text>
          <TextInput
            testID={`project-materials-${idx}`}
            value={p.materials_used || ""}
            onChangeText={(t) => update(p.id, { materials_used: t })}
            placeholder="e.g. 4 gal SW ProClassic, painter's tape"
            placeholderTextColor={colors.muted}
            style={[styles.input, styles.multi]}
            multiline
          />

          <View style={styles.touchUpRow}>
            <View>
              <Text style={styles.touchUpLabel}>Touch-ups needed</Text>
              <Text style={styles.touchUpHint}>Mark this project for a return visit</Text>
            </View>
            <Switch
              testID={`project-touchup-${idx}`}
              value={!!p.touch_up}
              onValueChange={(v) =>
                update(p.id, { touch_up: v, priority_flag: v ? "Touch-Ups" : p.priority_flag })
              }
              trackColor={{ true: colors.brandPrimary, false: colors.borderStrong }}
            />
          </View>

          <Pressable
            testID={`project-flag-toggle-${idx}`}
            onPress={() => setOpenFlagPickerFor(openFlagPickerFor === p.id ? null : p.id)}
            style={styles.flagPickerBtn}
          >
            <Ionicons name="flag" size={14} color={colors.brandPrimary} />
            <Text style={styles.flagPickerBtnText}>
              {p.priority_flag ? `Flag: ${p.priority_flag}` : "Set project flag (optional)"}
            </Text>
            <Ionicons
              name={openFlagPickerFor === p.id ? "chevron-up" : "chevron-down"}
              size={14}
              color={colors.brandPrimary}
            />
          </Pressable>
          {openFlagPickerFor === p.id && (
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              style={styles.flagChipsRow}
              contentContainerStyle={{ gap: 6, paddingVertical: 4 }}
              testID={`project-flag-chips-${idx}`}
            >
              <Pressable
                onPress={() => {
                  update(p.id, { priority_flag: null });
                  setOpenFlagPickerFor(null);
                }}
                style={[styles.flagChip, !p.priority_flag && styles.flagChipActive]}
              >
                <Text style={[styles.flagChipText, !p.priority_flag && styles.flagChipTextActive]}>
                  None
                </Text>
              </Pressable>
              {PRIORITY_FLAGS.map((f) => (
                <Pressable
                  key={f.type}
                  testID={`project-flag-${idx}-${f.type}`}
                  onPress={() => {
                    update(p.id, {
                      priority_flag: f.type,
                      touch_up: f.type === "Touch-Ups" ? true : p.touch_up,
                    });
                    setOpenFlagPickerFor(null);
                  }}
                  style={[styles.flagChip, p.priority_flag === f.type && styles.flagChipActive]}
                >
                  <Text
                    style={[
                      styles.flagChipText,
                      p.priority_flag === f.type && styles.flagChipTextActive,
                    ]}
                  >
                    {f.type}
                  </Text>
                </Pressable>
              ))}
            </ScrollView>
          )}

          {p.photos && p.photos.length > 0 ? (
            <Text style={styles.photosLabel}>📎 {p.photos.length} photo(s) from map</Text>
          ) : null}
        </View>
        );
      })}

      <Pressable testID="add-another-project" onPress={add} style={styles.addBtn}>
        <Ionicons name="add-circle" size={20} color={colors.onBrandPrimary} />
        <Text style={styles.addBtnText}>Add another Project</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginTop: spacing.lg },
  sectionHeaderRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: spacing.xs,
  },
  sectionTitleWrap: { flexDirection: "row", alignItems: "center", gap: 6 },
  sectionTitle: { fontSize: 15, fontWeight: "800", color: colors.onSurface },
  count: {
    backgroundColor: colors.brandTertiary,
    color: colors.onBrandTertiary,
    fontSize: 11,
    fontWeight: "800",
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: radius.pill,
    overflow: "hidden",
  },
  hint: { color: colors.muted, fontSize: 12, marginBottom: spacing.sm, lineHeight: 16 },
  card: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    marginBottom: spacing.md,
    gap: 4,
  },
  cardHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: spacing.xs,
  },
  cardTitle: { fontSize: 13, fontWeight: "800", color: colors.brandPrimary, textTransform: "uppercase" },
  micBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: radius.pill,
  },
  micBtnRecording: { backgroundColor: colors.error },
  micBtnText: { color: colors.onBrandPrimary, fontWeight: "800", fontSize: 11 },
  label: {
    color: colors.onSurfaceTertiary,
    fontSize: 12,
    fontWeight: "700",
    marginTop: spacing.sm,
    marginBottom: 4,
  },
  input: {
    backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.md,
    padding: spacing.md - 2,
    color: colors.onSurface,
    borderWidth: 1,
    borderColor: colors.border,
    fontSize: 13,
  },
  multi: { minHeight: 60, textAlignVertical: "top" },
  row2: { flexDirection: "row", gap: spacing.sm },
  coordText: {
    fontSize: 11,
    color: colors.muted,
    marginTop: 4,
    fontStyle: "italic",
  },
  touchUpRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: spacing.md,
    padding: spacing.sm,
    backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.md,
  },
  touchUpLabel: { color: colors.onSurface, fontSize: 13, fontWeight: "700" },
  touchUpHint: { color: colors.muted, fontSize: 11, marginTop: 2 },
  flagPickerBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginTop: spacing.sm,
    padding: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceTertiary,
    borderWidth: 1,
    borderColor: colors.border,
  },
  flagPickerBtnText: { flex: 1, color: colors.onSurface, fontSize: 12, fontWeight: "700" },
  flagChipsRow: { marginTop: spacing.xs },
  flagChip: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceTertiary,
    borderWidth: 1,
    borderColor: colors.border,
  },
  flagChipActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  flagChipText: { color: colors.onSurfaceTertiary, fontSize: 11, fontWeight: "700" },
  flagChipTextActive: { color: colors.onBrandPrimary },
  photosLabel: {
    color: colors.muted,
    fontSize: 11,
    marginTop: spacing.sm,
    fontStyle: "italic",
  },
  addBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    backgroundColor: colors.brandPrimary,
    padding: spacing.md,
    borderRadius: radius.md,
    marginTop: spacing.xs,
  },
  addBtnText: { color: colors.onBrandPrimary, fontWeight: "800", fontSize: 14 },
});
