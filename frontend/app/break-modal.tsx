import { useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  TextInput,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { colors, spacing, radius } from "@/src/theme";
import { useCustomLists } from "@/src/hooks/useCustomLists";

export default function BreakModal() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { break_types } = useCustomLists();
  const initial = break_types[0] || "Bathroom";
  const [type, setType] = useState<string>(initial);
  const [reason, setReason] = useState("");
  const [callDetails, setCallDetails] = useState("");
  const [saving, setSaving] = useState(false);

  // Keep the selected type valid when custom lists load in.
  const selected = break_types.includes(type) ? type : (break_types[0] || "Bathroom");

  const save = async () => {
    setSaving(true);
    try {
      await api.startBreak({
        break_type: selected,
        reason: reason || selected,
        call_details: selected === "Admin Call" ? callDetails : null,
      });
      router.back();
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
        <Pressable onPress={() => router.back()} testID="break-close">
          <Ionicons name="close" size={26} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Start Break</Text>
        <View style={{ width: 26 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg }} keyboardShouldPersistTaps="handled">
        <Text style={styles.label}>Break Type</Text>
        <View style={styles.grid}>
          {break_types.map((t) => (
            <Pressable
              key={t}
              testID={`break-type-${t}`}
              onPress={() => setType(t)}
              style={[styles.chip, selected === t && styles.chipSelected]}
            >
              <Text style={[styles.chipText, selected === t && styles.chipTextSelected]}>{t}</Text>
            </Pressable>
          ))}
        </View>

        <Text style={styles.label}>Reason / Notes</Text>
        <TextInput
          testID="break-reason"
          value={reason}
          onChangeText={setReason}
          placeholder="Explain the break (auditable log)"
          placeholderTextColor={colors.muted}
          style={[styles.input, { minHeight: 80, textAlignVertical: "top" }]}
          multiline
        />

        {selected === "Admin Call" && (
          <>
            <Text style={styles.label}>Call Details</Text>
            <TextInput
              testID="break-call-details"
              value={callDetails}
              onChangeText={setCallDetails}
              placeholder="Who called, what was discussed, time frames"
              placeholderTextColor={colors.muted}
              style={[styles.input, { minHeight: 100, textAlignVertical: "top" }]}
              multiline
            />
          </>
        )}

        <Pressable
          testID="break-save"
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
            <Text style={styles.primaryBtnText}>Start Break</Text>
          )}
        </Pressable>
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
  label: {
    color: colors.onSurfaceTertiary,
    fontSize: 13,
    fontWeight: "700",
    marginTop: spacing.md,
    marginBottom: spacing.sm,
  },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
  },
  chipSelected: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { color: colors.onSurface, fontWeight: "600", fontSize: 13 },
  chipTextSelected: { color: colors.onBrandPrimary },
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
    marginTop: spacing.xl,
    backgroundColor: colors.brandPrimary,
    padding: spacing.md + 2,
    borderRadius: radius.md,
    alignItems: "center",
  },
  primaryBtnText: { color: colors.onBrandPrimary, fontWeight: "700", fontSize: 16 },
});
