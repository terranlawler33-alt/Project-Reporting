import { View, StyleSheet } from "react-native";
import MapView, { Marker, PROVIDER_DEFAULT } from "react-native-maps";
import { colors, radius } from "@/src/theme";

type Visit = {
  id: string;
  latitude: number;
  longitude: number;
  customer_name?: string | null;
  ended_at?: string | null;
};

export function PaintOpsMap({ visits }: { visits: Visit[] }) {
  const active = visits.filter((v) => !v.ended_at);
  const first = visits[0];
  const region = first
    ? {
        latitude: first.latitude,
        longitude: first.longitude,
        latitudeDelta: 0.05,
        longitudeDelta: 0.05,
      }
    : {
        latitude: 40.7128,
        longitude: -74.006,
        latitudeDelta: 0.5,
        longitudeDelta: 0.5,
      };
  return (
    <View style={styles.wrap}>
      <MapView
        style={StyleSheet.absoluteFill}
        provider={PROVIDER_DEFAULT}
        initialRegion={region}
        showsUserLocation
      >
        {visits.map((v) => (
          <Marker
            key={v.id}
            coordinate={{ latitude: v.latitude, longitude: v.longitude }}
            title={v.customer_name || "Job Site"}
            description={v.ended_at ? "Completed" : "Active"}
            pinColor={v.ended_at ? colors.success : colors.brandPrimary}
          />
        ))}
      </MapView>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, borderRadius: radius.md, overflow: "hidden" },
});
