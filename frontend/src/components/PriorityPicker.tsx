import { View, Text, StyleSheet, Pressable, TextInput } from "react-native";
import { PRIORITY_LEVELS, PRIORITY_FLAGS, flagRequiresReason, priorityLevelColor } from "@/src/priority";
import { colors, spacing, radius } from "@/src/theme";

export type PriorityFlagEntry = { type: string; reason?: string };

export function PriorityPicker({
  level,
  onLevelChange,
  flags,
  onFlagsChange,
}: {
  level: string | null;
  onLevelChange: (l: string | null) => void;
  flags: PriorityFlagEntry[];
  onFlagsChange: (next: PriorityFlagEntry[]) => void;
}) {
  const isFlagSelected = (t: string) => flags.some((f) => f.type === t);

  const toggleFlag = (t: string) => {
    if (isFlagSelected(t)) {
      onFlagsChange(flags.filter((f) => f.type !== t));
    } else {
      onFlagsChange([...flags, { type: t, reason: "" }]);
    }
  };

  const setReason = (t: string, reason: string) => {
    onFlagsChange(flags.map((f) => (f.type === t ? { ...f, reason } : f)));
  };

  return (
    <View style={styles.wrap} testID="priority-picker">
      <Text style={styles.label}>Priority Level</Text>
      <View style={styles.row}>
        <Pressable
          testID="priority-level-none"
          onPress={() => onLevelChange(null)}
          style={[styles.chip, !level && styles.chipSelected]}
        >
          <Text style={[styles.chipText, !level && styles.chipTextSelected]}>None</Text>
        </Pressable>
        {PRIORITY_LEVELS.map((l) => {
          const active = level === l;
          const { bg, text } = priorityLevelColor(l);
          return (
            <Pressable
              key={l}
              testID={`priority-level-${l}`}
              onPress={() => onLevelChange(l)}
              style={[
                styles.chip,
                active && { backgroundColor: bg, borderColor: bg },
              ]}
            >
              <Text
                style={[
                  styles.chipText,
                  active && { color: text },
                ]}
              >
                {l}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <Text style={styles.label}>Flag details for the owner (select any)</Text>
      <View style={styles.flagList}>
        {PRIORITY_FLAGS.map((f) => {
          const selected = isFlagSelected(f.type);
          const entry = flags.find((x) => x.type === f.type);
          return (
            <View key={f.type} style={styles.flagWrap}>
              <Pressable
                testID={`priority-flag-${f.type}`}
                onPress={() => toggleFlag(f.type)}
                style={[styles.flagChip, selected && styles.flagChipSelected]}
              >
                <Text style={[styles.flagChipText, selected && { color: colors.onError }]}>
                  {selected ? "☑ " : "☐ "}
                  {f.type}
                  {f.requiresReason ? " *" : ""}
                </Text>
              </Pressable>
              {selected && f.requiresReason ? (
                <TextInput
                  testID={`priority-reason-${f.type}`}
                  value={entry?.reason || ""}
                  onChangeText={(t) => setReason(f.type, t)}
                  placeholder={`Reason for ${f.type} — will appear red under Delay/Constraints`}
                  placeholderTextColor={colors.muted}
                  style={styles.reasonInput}
                  multiline
                />
              ) : null}
            </View>
          );
        })}
      </View>
      <Text style={styles.footNote}>* Types marked with an asterisk require a reason.</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.xs, marginTop: spacing.md },
  label: {
    color: colors.onSurfaceTertiary,
    fontSize: 13,
    fontWeight: "700",
    marginTop: spacing.md,
    marginBottom: spacing.xs,
  },
  row: { flexDirection: "row", gap: spacing.xs, flexWrap: "wrap" },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
    height: 36,
    justifyContent: "center",
  },
  chipSelected: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { color: colors.onSurface, fontWeight: "700", fontSize: 12 },
  chipTextSelected: { color: colors.onBrandPrimary },
  flagList: { gap: spacing.xs },
  flagWrap: { gap: 4 },
  flagChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
  },
  flagChipSelected: { backgroundColor: colors.error, borderColor: colors.error },
  flagChipText: { color: colors.onSurface, fontWeight: "600", fontSize: 13 },
  reasonInput: {
    backgroundColor: "#FEE2E2",
    borderRadius: radius.md,
    padding: spacing.md,
    color: colors.error,
    borderWidth: 1,
    borderColor: colors.error,
    fontSize: 14,
    minHeight: 60,
    textAlignVertical: "top",
    fontWeight: "600",
  },
  footNote: { color: colors.muted, fontSize: 11, marginTop: spacing.xs, fontStyle: "italic" },
});
