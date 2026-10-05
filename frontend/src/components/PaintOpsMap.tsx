import { forwardRef, useImperativeHandle, useRef, useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, Modal } from "react-native";
import MapView, { Marker, PROVIDER_DEFAULT, Callout } from "react-native-maps";
import Ionicons from "@react-native-vector-icons/ionicons";
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
  is_flagged?: boolean;
};

export type PaintOpsMapHandle = {
  focusVisit: (v: Visit) => void;
};

type Props = {
  visits: Visit[];
  selectedId?: string | null;
  onMarkerPress?: (v: Visit) => void;
};

function pinColorFor(v: Visit, selected: boolean): string {
  if (selected) return colors.warning;
  if (v.is_flagged) return colors.error;         // flagged → red
  if (!v.ended_at) return "#F97316";              // in-progress → orange
  return colors.success;                          // complete → green
}

function MapCore({
  visits,
  selectedId,
  onMarkerPress,
  mapRef,
  initialRegion,
}: Props & {
  mapRef: React.RefObject<MapView | null>;
  initialRegion: {
    latitude: number;
    longitude: number;
    latitudeDelta: number;
    longitudeDelta: number;
  };
}) {
  return (
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
            pinColor={pinColorFor(v, isSelected)}
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
  );
}

export const PaintOpsMap = forwardRef<PaintOpsMapHandle, Props>(function PaintOpsMap(
  { visits, selectedId, onMarkerPress },
  ref,
) {
  const [fullscreen, setFullscreen] = useState(false);
  const mapRef = useRef<MapView | null>(null);
  const fsMapRef = useRef<MapView | null>(null);

  const first = visits[0];
  const initialRegion = first
    ? {
        latitude: first.latitude,
        longitude: first.longitude,
        latitudeDelta: 0.05,
        longitudeDelta: 0.05,
      }
    : { latitude: 40.7128, longitude: -74.006, latitudeDelta: 0.5, longitudeDelta: 0.5 };

  useImperativeHandle(ref, () => ({
    focusVisit: (v: Visit) => {
      const target = fullscreen ? fsMapRef.current : mapRef.current;
      target?.animateToRegion(
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
    if (!v) return;
    const target = fullscreen ? fsMapRef.current : mapRef.current;
    target?.animateToRegion(
      {
        latitude: v.latitude,
        longitude: v.longitude,
        latitudeDelta: 0.015,
        longitudeDelta: 0.015,
      },
      400,
    );
  }, [selectedId, visits, fullscreen]);

  return (
    <View style={styles.wrap} testID="live-map-native">
      <MapCore
        visits={visits}
        selectedId={selectedId}
        onMarkerPress={onMarkerPress}
        mapRef={mapRef}
        initialRegion={initialRegion}
      />
      <Pressable
        testID="map-fullscreen-btn"
        onPress={() => setFullscreen(true)}
        style={styles.expandBtn}
        hitSlop={6}
      >
        <Ionicons name="expand" size={18} color={colors.onSurface} />
      </Pressable>

      <Modal
        visible={fullscreen}
        animationType="slide"
        onRequestClose={() => setFullscreen(false)}
      >
        <View style={styles.fsWrap} testID="map-fullscreen-modal">
          <MapCore
            visits={visits}
            selectedId={selectedId}
            onMarkerPress={onMarkerPress}
            mapRef={fsMapRef}
            initialRegion={initialRegion}
          />
          <Pressable
            testID="map-fullscreen-close"
            onPress={() => setFullscreen(false)}
            style={styles.fsCloseBtn}
            hitSlop={8}
          >
            <Ionicons name="close" size={22} color="#fff" />
          </Pressable>
          <View style={styles.fsLegend}>
            <Text style={styles.fsLegendText}>
              {visits.length} pin{visits.length === 1 ? "" : "s"} · tap ✕ to close
            </Text>
          </View>
        </View>
      </Modal>
    </View>
  );
});

const styles = StyleSheet.create({
  wrap: { flex: 1, borderRadius: radius.md, overflow: "hidden" },
  callout: { minWidth: 180, maxWidth: 240, padding: spacing.xs },
  calloutTitle: { fontWeight: "700", color: colors.onSurface, fontSize: 13 },
  calloutSub: { color: colors.muted, fontSize: 11, marginTop: 2 },
  calloutNotes: {
    color: colors.onSurfaceTertiary,
    fontSize: 11,
    marginTop: 4,
    fontStyle: "italic",
  },
  expandBtn: {
    position: "absolute",
    top: spacing.sm,
    right: spacing.sm,
    width: 34,
    height: 34,
    borderRadius: radius.md,
    backgroundColor: "rgba(255,255,255,0.95)",
    alignItems: "center",
    justifyContent: "center",
    shadowColor: "#000",
    shadowOpacity: 0.15,
    shadowRadius: 4,
    shadowOffset: { width: 0, height: 2 },
    elevation: 4,
  },
  fsWrap: { flex: 1, backgroundColor: "#000" },
  fsCloseBtn: {
    position: "absolute",
    top: 44,
    right: spacing.lg,
    width: 42,
    height: 42,
    borderRadius: 21,
    backgroundColor: "rgba(17,24,39,0.85)",
    alignItems: "center",
    justifyContent: "center",
  },
  fsLegend: {
    position: "absolute",
    bottom: 30,
    alignSelf: "center",
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    backgroundColor: "rgba(17,24,39,0.85)",
    borderRadius: radius.pill,
  },
  fsLegendText: { color: "#fff", fontSize: 12, fontWeight: "700" },
});
