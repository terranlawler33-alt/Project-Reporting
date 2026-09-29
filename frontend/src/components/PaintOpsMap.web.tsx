import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { colors, spacing, radius } from "@/src/theme";

type Visit = {
  id: string;
  latitude: number;
  longitude: number;
  customer_name?: string | null;
  address?: string | null;
  ended_at?: string | null;
};

// Web fallback: react-native-maps doesn't render on web. Show a compact grid of pins with coords.
export function PaintOpsMap({ visits }: { visits: Visit[] }) {
  return (
    <View style={styles.wrap} testID="web-map-fallback">
      <View style={styles.bg}>
        <Ionicons name="map" size={64} color={colors.brandTertiary} />
        <Text style={styles.hint}>Live map (native only) — showing pins list</Text>
      </View>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.chips}
      >
        {visits.length === 0 ? (
          <View style={styles.chip}>
            <Ionicons name="location-outline" size={12} color={colors.muted} />
            <Text style={styles.chipEmpty}>No pins today</Text>
          </View>
        ) : (
          visits.map((v) => (
            <Pressable
              key={v.id}
              style={[styles.chip, v.ended_at ? styles.chipDone : styles.chipActive]}
            >
              <Ionicons
                name="location"
                size={12}
                color={v.ended_at ? colors.onSuccess : colors.onBrandPrimary}
              />
              <Text
                style={[
                  styles.chipText,
                  { color: v.ended_at ? colors.onSuccess : colors.onBrandPrimary },
                ]}
                numberOfLines={1}
              >
                {v.customer_name || `${v.latitude.toFixed(3)}, ${v.longitude.toFixed(3)}`}
              </Text>
            </Pressable>
          ))
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: colors.surfaceTertiary, justifyContent: "space-between" },
  bg: { flex: 1, alignItems: "center", justifyContent: "center", gap: spacing.sm },
  hint: { color: colors.muted, fontSize: 12 },
  chips: { padding: spacing.sm, gap: spacing.xs, flexDirection: "row" },
  chip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: spacing.sm,
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
    maxWidth: 180,
    flexShrink: 0,
  },
  chipActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipDone: { backgroundColor: colors.success, borderColor: colors.success },
  chipText: { fontSize: 11, fontWeight: "700" },
  chipEmpty: { color: colors.muted, fontSize: 12 },
});
