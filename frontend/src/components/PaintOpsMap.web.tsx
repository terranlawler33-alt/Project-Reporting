import { forwardRef, useImperativeHandle } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { colors, spacing, radius } from "@/src/theme";

export type Visit = {
  id: string;
  latitude: number;
  longitude: number;
  customer_name?: string | null;
  address?: string | null;
  project_code?: string | null;
  notes?: string | null;
  ended_at?: string | null;
};

export type PaintOpsMapHandle = {
  focusVisit: (v: Visit) => void;
};

type Props = {
  visits: Visit[];
  selectedId?: string | null;
  onMarkerPress?: (v: Visit) => void;
};

// Web fallback: react-native-maps doesn't work on web.
// Show a scrollable strip of pin chips so users get a "map-like" glance.
export const PaintOpsMap = forwardRef<PaintOpsMapHandle, Props>(function PaintOpsMap(
  { visits, selectedId, onMarkerPress },
  ref,
) {
  useImperativeHandle(ref, () => ({ focusVisit: () => {} }));

  return (
    <View style={styles.wrap} testID="web-map-fallback">
      <View style={styles.bg}>
        <Ionicons name="map" size={64} color={colors.brandTertiary} />
        <Text style={styles.hint}>Live map — available on iOS & Android build</Text>
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
          visits.map((v) => {
            const isSelected = v.id === selectedId;
            return (
              <Pressable
                key={v.id}
                testID={`web-pin-${v.id}`}
                onPress={() => onMarkerPress?.(v)}
                style={[
                  styles.chip,
                  v.ended_at ? styles.chipDone : styles.chipActive,
                  isSelected && styles.chipSelected,
                ]}
              >
                <Ionicons
                  name="location"
                  size={12}
                  color={
                    isSelected
                      ? colors.onWarning
                      : v.ended_at
                      ? colors.onSuccess
                      : colors.onBrandPrimary
                  }
                />
                <Text
                  style={[
                    styles.chipText,
                    {
                      color: isSelected
                        ? colors.onWarning
                        : v.ended_at
                        ? colors.onSuccess
                        : colors.onBrandPrimary,
                    },
                  ]}
                  numberOfLines={1}
                >
                  {v.customer_name || `${v.latitude.toFixed(3)}, ${v.longitude.toFixed(3)}`}
                </Text>
              </Pressable>
            );
          })
        )}
      </ScrollView>
    </View>
  );
});

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
  chipSelected: { backgroundColor: colors.warning, borderColor: colors.warning },
  chipText: { fontSize: 11, fontWeight: "700" },
  chipEmpty: { color: colors.muted, fontSize: 12 },
});
