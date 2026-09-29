import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { colors, spacing, radius } from "@/src/theme";

export function RecipientGroupPicker({
  onPick,
  testID = "group-picker",
}: {
  onPick: (emails: string[], groupName: string) => void;
  testID?: string;
}) {
  const [groups, setGroups] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listGroups()
      .then(setGroups)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return null;
  if (groups.length === 0) return null;

  return (
    <View style={styles.wrap} testID={testID}>
      <View style={styles.header}>
        <Ionicons name="people" size={14} color={colors.brandPrimary} />
        <Text style={styles.title}>Pick a group</Text>
      </View>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.row}
      >
        {groups.map((g) => (
          <Pressable
            key={g.id}
            testID={`${testID}-group-${g.id}`}
            onPress={() => onPick(g.emails || [], g.name)}
            style={styles.chip}
          >
            <Text style={styles.chipText}>{g.name}</Text>
            <Text style={styles.chipCount}>{(g.emails || []).length}</Text>
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.xs, marginTop: spacing.xs },
  header: { flexDirection: "row", alignItems: "center", gap: 4 },
  title: { color: colors.brandPrimary, fontSize: 12, fontWeight: "700" },
  row: { gap: spacing.xs, paddingRight: spacing.md },
  chip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    borderWidth: 1,
    borderColor: colors.brandTertiary,
    height: 36,
    flexShrink: 0,
  },
  chipText: { color: colors.onBrandTertiary, fontWeight: "700", fontSize: 12 },
  chipCount: {
    color: colors.onBrandTertiary,
    fontSize: 11,
    fontWeight: "700",
    backgroundColor: "rgba(255,255,255,0.4)",
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    textAlign: "center",
    lineHeight: 18,
    paddingHorizontal: 4,
    overflow: "hidden",
  },
});
