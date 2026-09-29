import { forwardRef, useImperativeHandle, useRef, useEffect } from "react";
import { View, StyleSheet } from "react-native";
import MapView, { Marker, PROVIDER_DEFAULT, Callout } from "react-native-maps";
import { Text } from "react-native";
import { colors, radius, spacing } from "@/src/theme";

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

export const PaintOpsMap = forwardRef<PaintOpsMapHandle, Props>(function PaintOpsMap(
  { visits, selectedId, onMarkerPress },
  ref,
) {
  const mapRef = useRef<MapView>(null);
  const first = visits[0];
  const initialRegion = first
    ? { latitude: first.latitude, longitude: first.longitude, latitudeDelta: 0.05, longitudeDelta: 0.05 }
    : { latitude: 40.7128, longitude: -74.006, latitudeDelta: 0.5, longitudeDelta: 0.5 };

  useImperativeHandle(ref, () => ({
    focusVisit: (v: Visit) => {
      mapRef.current?.animateToRegion(
        {
          latitude: v.latitude,
          longitude: v.longitude,
          latitudeDelta: 0.015,
          longitudeDelta: 0.015,
        },
        400,
      );
    },
  }));

  // Follow selectedId externally
  useEffect(() => {
    if (!selectedId) return;
    const v = visits.find((x) => x.id === selectedId);
    if (v) {
      mapRef.current?.animateToRegion(
        {
          latitude: v.latitude,
          longitude: v.longitude,
          latitudeDelta: 0.015,
          longitudeDelta: 0.015,
        },
        400,
      );
    }
  }, [selectedId, visits]);

  return (
    <View style={styles.wrap}>
      <MapView
        ref={mapRef}
        style={StyleSheet.absoluteFill}
        provider={PROVIDER_DEFAULT}
        initialRegion={initialRegion}
        showsUserLocation
      >
        {visits.map((v) => {
          const isSelected = v.id === selectedId;
          return (
            <Marker
              key={v.id}
              identifier={v.id}
              coordinate={{ latitude: v.latitude, longitude: v.longitude }}
              onPress={() => onMarkerPress?.(v)}
              pinColor={isSelected ? colors.warning : v.ended_at ? colors.success : colors.brandPrimary}
            >
              <Callout>
                <View style={styles.callout}>
                  <Text style={styles.calloutTitle} numberOfLines={1}>
                    {v.customer_name || "Job Site"}
                    {v.project_code ? ` · ${v.project_code}` : ""}
                  </Text>
                  {v.address ? (
                    <Text style={styles.calloutSub} numberOfLines={2}>
                      {v.address}
                    </Text>
                  ) : (
                    <Text style={styles.calloutSub}>
                      {v.latitude.toFixed(4)}, {v.longitude.toFixed(4)}
                    </Text>
                  )}
                  {v.notes ? (
                    <Text style={styles.calloutNotes} numberOfLines={3}>
                      {v.notes}
                    </Text>
                  ) : null}
                </View>
              </Callout>
            </Marker>
          );
        })}
      </MapView>
    </View>
  );
});

const styles = StyleSheet.create({
  wrap: { flex: 1, borderRadius: radius.md, overflow: "hidden" },
  callout: { minWidth: 180, maxWidth: 240, padding: spacing.xs },
  calloutTitle: { fontWeight: "700", color: colors.onSurface, fontSize: 13 },
  calloutSub: { color: colors.muted, fontSize: 11, marginTop: 2 },
  calloutNotes: { color: colors.onSurfaceTertiary, fontSize: 11, marginTop: 4, fontStyle: "italic" },
});
