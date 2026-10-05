import { forwardRef, useImperativeHandle, useRef, useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, Modal } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { MapContainer, TileLayer, Marker, Popup, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { colors, spacing, radius } from "@/src/theme";

// Leaflet's default marker images don't ship with the JS bundle — point them at the CDN.
// This is a one-time, safe global fix.
const iconProto: any = (L as any).Icon.Default.prototype;
if (iconProto._getIconUrl) delete iconProto._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/images/marker-shadow.png",
});

// Colored SVG divIcon so active vs completed pins are distinguishable at a glance.
function coloredPinIcon(fill: string) {
  return L.divIcon({
    className: "paintops-pin",
    html: `<div style="width:24px;height:32px;display:flex;align-items:center;justify-content:center;">
      <svg width="22" height="30" viewBox="0 0 22 30" xmlns="http://www.w3.org/2000/svg">
        <path d="M11 0C4.925 0 0 4.925 0 11c0 8.25 11 19 11 19s11-10.75 11-19c0-6.075-4.925-11-11-11z" fill="${fill}" stroke="#fff" stroke-width="1.5"/>
        <circle cx="11" cy="11" r="4.2" fill="#fff"/>
      </svg>
    </div>`,
    iconSize: [22, 30],
    iconAnchor: [11, 30],
    popupAnchor: [0, -28],
  });
}

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
  if (v.is_flagged) return colors.error;        // flagged → red
  if (!v.ended_at) return "#F97316";             // in-progress → orange
  return colors.success;                         // complete → green
}

// Small helper component that lives INSIDE the MapContainer so we can imperatively
// pan/zoom via the parent's forwarded ref.
function MapController({
  onReady,
}: {
  onReady: (map: L.Map) => void;
}) {
  const map = useMap();
  useEffect(() => {
    onReady(map);
    // Ensure the map recalculates its size once it's actually laid out
    setTimeout(() => map.invalidateSize(), 100);
    setTimeout(() => map.invalidateSize(), 500);
  }, [map, onReady]);
  return null;
}

function MapCore({
  visits,
  selectedId,
  onMarkerPress,
  mapReady,
}: {
  visits: Visit[];
  selectedId?: string | null;
  onMarkerPress?: (v: Visit) => void;
  mapReady: (m: L.Map) => void;
}) {
  const first = visits[0];
  const center: [number, number] = first
    ? [first.latitude, first.longitude]
    : [40.7128, -74.006];
  const zoom = first ? 11 : 4;

  return (
    <MapContainer
      // @ts-expect-error - types quirk in react-leaflet 5 declarations
      center={center}
      zoom={zoom}
      style={{ width: "100%", height: "100%" }}
      scrollWheelZoom
    >
      <MapController onReady={mapReady} />
      <TileLayer
        // @ts-expect-error - types quirk
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {visits.map((v) => {
        const isSelected = v.id === selectedId;
        const color = pinColorFor(v, isSelected);
        return (
          <Marker
            key={v.id}
            position={[v.latitude, v.longitude]}
            icon={coloredPinIcon(color)}
            // @ts-expect-error - eventHandlers is valid but not in the type shim
            eventHandlers={{
              click: () => onMarkerPress?.(v),
            }}
          >
            <Popup>
              <div style={{ minWidth: 180, maxWidth: 240 }}>
                <div style={{ fontWeight: 700, fontSize: 13, color: "#111827" }}>
                  {v.customer_name || "Job Site"}
                  {v.project_code ? ` · ${v.project_code}` : ""}
                </div>
                <div style={{ color: "#6B7280", fontSize: 11, marginTop: 2 }}>
                  {v.address ||
                    `${v.latitude.toFixed(4)}, ${v.longitude.toFixed(4)}`}
                </div>
                {v.notes ? (
                  <div style={{ color: "#374151", fontSize: 11, marginTop: 4, fontStyle: "italic" }}>
                    {v.notes.slice(0, 140)}
                  </div>
                ) : null}
              </div>
            </Popup>
          </Marker>
        );
      })}
    </MapContainer>
  );
}

export const PaintOpsMap = forwardRef<PaintOpsMapHandle, Props>(function PaintOpsMap(
  { visits, selectedId, onMarkerPress },
  ref,
) {
  const [fullscreen, setFullscreen] = useState(false);
  const mapRef = useRef<L.Map | null>(null);
  const fsMapRef = useRef<L.Map | null>(null);

  useImperativeHandle(ref, () => ({
    focusVisit: (v: Visit) => {
      const target = fullscreen ? fsMapRef.current : mapRef.current;
      target?.setView([v.latitude, v.longitude], 15, { animate: true });
    },
  }));

  return (
    <View style={styles.wrap} testID="live-map-webview">
      <MapCore
        visits={visits}
        selectedId={selectedId}
        onMarkerPress={onMarkerPress}
        mapReady={(m) => (mapRef.current = m)}
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
            mapReady={(m) => (fsMapRef.current = m)}
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
  wrap: {
    flex: 1,
    borderRadius: radius.md,
    overflow: "hidden",
    backgroundColor: colors.surfaceTertiary,
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
    zIndex: 400,
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
    zIndex: 500,
  },
  fsLegend: {
    position: "absolute",
    bottom: 30,
    alignSelf: "center",
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    backgroundColor: "rgba(17,24,39,0.85)",
    borderRadius: radius.pill,
    zIndex: 500,
  },
  fsLegendText: { color: "#fff", fontSize: 12, fontWeight: "700" },
});
