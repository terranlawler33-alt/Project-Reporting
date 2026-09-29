import { useCallback, useEffect, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ScrollView,
  TextInput,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Location from "expo-location";
import Ionicons from "@react-native-vector-icons/ionicons";
import * as Haptics from "expo-haptics";
import { useFocusEffect } from "expo-router";
import { api } from "@/src/api";
import { colors, spacing, radius } from "@/src/theme";
import { PaintOpsMap } from "@/src/components/PaintOpsMap";

export default function MapScreen() {
  const insets = useSafeAreaInsets();
  const [visits, setVisits] = useState<any[]>([]);
  const [customers, setCustomers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [gpsLoading, setGpsLoading] = useState(false);
  const [showCustomerPicker, setShowCustomerPicker] = useState(false);
  const [form, setForm] = useState({
    latitude: "",
    longitude: "",
    customer_name: "",
    address: "",
    project_code: "",
    notes: "",
  });

  const load = useCallback(async () => {
    try {
      const [v, c] = await Promise.all([api.visitsToday(), api.listCustomers().catch(() => [])]);
      setVisits(v);
      setCustomers(c);
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const captureGps = async () => {
    setGpsLoading(true);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== "granted") throw new Error("Permission denied");
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
      setForm((f) => ({
        ...f,
        latitude: pos.coords.latitude.toFixed(6),
        longitude: pos.coords.longitude.toFixed(6),
      }));
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } catch {
      setForm((f) => ({ ...f, latitude: "40.712800", longitude: "-74.006000" }));
    } finally {
      setGpsLoading(false);
    }
  };

  const pickCustomer = (c: any) => {
    setForm((f) => ({
      ...f,
      customer_name: c.name,
      address: c.address || f.address,
      project_code: c.project_code || f.project_code,
    }));
    setShowCustomerPicker(false);
  };

  const saveVisit = async () => {
    if (!form.latitude || !form.longitude) return;
    setSaving(true);
    try {
      await api.createVisit({
        latitude: parseFloat(form.latitude),
        longitude: parseFloat(form.longitude),
        customer_name: form.customer_name || null,
        address: form.address || null,
        project_code: form.project_code || null,
        notes: form.notes || null,
      });
      setForm({ latitude: "", longitude: "", customer_name: "", address: "", project_code: "", notes: "" });
      setShowForm(false);
      await load();
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
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
        <View style={{ flex: 1 }}>
          <Text style={styles.headerTitle}>Interaction Map</Text>
          <Text style={styles.headerSub}>GPS-tracked job sites</Text>
        </View>
        <Pressable
          testID="new-visit-toggle"
          onPress={() => setShowForm((s) => !s)}
          style={styles.headerBtn}
        >
          <Ionicons name={showForm ? "close" : "add"} size={22} color={colors.onBrandPrimary} />
        </Pressable>
      </View>

      <View style={styles.mapWrap} testID="live-map-container">
        <PaintOpsMap visits={visits} />
        <View style={styles.mapLegend}>
          <View style={styles.legendItem}>
            <View style={[styles.legendDot, { backgroundColor: colors.brandPrimary }]} />
            <Text style={styles.legendText}>Active</Text>
          </View>
          <View style={styles.legendItem}>
            <View style={[styles.legendDot, { backgroundColor: colors.success }]} />
            <Text style={styles.legendText}>Completed</Text>
          </View>
        </View>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: (insets.bottom || 0) + 100 }}
        keyboardShouldPersistTaps="handled"
      >
        {showForm && (
          <View style={styles.form} testID="visit-form">
            <Text style={styles.formTitle}>Check in at a location</Text>

            <View style={styles.gpsRow}>
              <TextInput
                testID="visit-lat"
                value={form.latitude}
                onChangeText={(t) => setForm((f) => ({ ...f, latitude: t }))}
                placeholder="Latitude"
                placeholderTextColor={colors.muted}
                style={[styles.input, { flex: 1 }]}
                keyboardType="numeric"
              />
              <TextInput
                testID="visit-lon"
                value={form.longitude}
                onChangeText={(t) => setForm((f) => ({ ...f, longitude: t }))}
                placeholder="Longitude"
                placeholderTextColor={colors.muted}
                style={[styles.input, { flex: 1 }]}
                keyboardType="numeric"
              />
              <Pressable testID="capture-gps" onPress={captureGps} style={styles.gpsBtn}>
                {gpsLoading ? (
                  <ActivityIndicator color={colors.onBrandPrimary} size="small" />
                ) : (
                  <Ionicons name="locate" size={18} color={colors.onBrandPrimary} />
                )}
              </Pressable>
            </View>

            {customers.length > 0 && (
              <Pressable
                testID="customer-picker-toggle"
                onPress={() => setShowCustomerPicker((s) => !s)}
                style={styles.pickerBtn}
              >
                <Ionicons name="people" size={16} color={colors.brandPrimary} />
                <Text style={styles.pickerBtnText}>
                  {showCustomerPicker ? "Hide directory" : `Pick from directory (${customers.length})`}
                </Text>
              </Pressable>
            )}
            {showCustomerPicker && (
              <View style={styles.pickerList} testID="customer-picker-list">
                {customers.map((c) => (
                  <Pressable
                    key={c.id}
                    testID={`pick-customer-${c.id}`}
                    onPress={() => pickCustomer(c)}
                    style={styles.pickerItem}
                  >
                    <Text style={styles.pickerName}>{c.name}</Text>
                    {c.address ? <Text style={styles.pickerMeta}>{c.address}</Text> : null}
                  </Pressable>
                ))}
              </View>
            )}

            <TextInput
              testID="visit-customer"
              value={form.customer_name}
              onChangeText={(t) => setForm((f) => ({ ...f, customer_name: t }))}
              placeholder="Customer name"
              placeholderTextColor={colors.muted}
              style={styles.input}
            />
            <TextInput
              testID="visit-address"
              value={form.address}
              onChangeText={(t) => setForm((f) => ({ ...f, address: t }))}
              placeholder="Street address"
              placeholderTextColor={colors.muted}
              style={styles.input}
            />
            <TextInput
              testID="visit-project"
              value={form.project_code}
              onChangeText={(t) => setForm((f) => ({ ...f, project_code: t }))}
              placeholder="Project code (e.g. P-1042)"
              placeholderTextColor={colors.muted}
              style={styles.input}
            />
            <TextInput
              testID="visit-notes"
              value={form.notes}
              onChangeText={(t) => setForm((f) => ({ ...f, notes: t }))}
              placeholder="Notes (tasks done, issues, materials)"
              placeholderTextColor={colors.muted}
              style={[styles.input, { minHeight: 80, textAlignVertical: "top" }]}
              multiline
            />

            <Pressable
              testID="save-visit"
              onPress={saveVisit}
              disabled={saving || !form.latitude || !form.longitude}
              style={({ pressed }) => [
                styles.primaryBtn,
                pressed && { opacity: 0.85 },
                (saving || !form.latitude || !form.longitude) && { opacity: 0.6 },
              ]}
            >
              {saving ? (
                <ActivityIndicator color={colors.onBrandPrimary} />
              ) : (
                <Text style={styles.primaryBtnText}>Save Visit</Text>
              )}
            </Pressable>
          </View>
        )}

        {loading ? (
          <ActivityIndicator color={colors.brandPrimary} />
        ) : visits.length === 0 ? (
          <View style={styles.empty}>
            <Ionicons name="location-outline" size={40} color={colors.muted} />
            <Text style={styles.emptyText}>No visits logged today</Text>
            <Text style={styles.emptySub}>Tap + to check in at a location.</Text>
          </View>
        ) : (
          visits.map((v) => (
            <View key={v.id} style={styles.visitCard} testID={`map-visit-${v.id}`}>
              <View style={[styles.pin, v.ended_at && { backgroundColor: colors.success }]}>
                <Ionicons name="location" size={18} color={colors.onBrandPrimary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.visitTitle}>
                  {v.customer_name || "Job Site"}
                  {v.project_code ? ` · ${v.project_code}` : ""}
                </Text>
                <Text style={styles.visitCoord}>
                  {v.address || `${v.latitude.toFixed(5)}, ${v.longitude.toFixed(5)}`}
                </Text>
                {v.notes ? <Text style={styles.visitNotes}>{v.notes}</Text> : null}
                <Text style={styles.visitTime}>
                  {new Date(v.timestamp).toLocaleTimeString()}
                  {v.ended_at ? ` → ${new Date(v.ended_at).toLocaleTimeString()}` : " · active"}
                </Text>
              </View>
              {!v.ended_at && (
                <Pressable
                  testID={`end-visit-${v.id}`}
                  onPress={async () => {
                    await api.endVisit(v.id);
                    await load();
                  }}
                  style={styles.endBtn}
                >
                  <Text style={styles.endBtnText}>End</Text>
                </Pressable>
              )}
            </View>
          ))
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  header: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
    flexDirection: "row",
    alignItems: "flex-end",
  },
  headerTitle: { fontSize: 24, fontWeight: "700", color: colors.onSurface },
  headerSub: { color: colors.muted, fontSize: 12, marginTop: 2 },
  headerBtn: {
    backgroundColor: colors.brandPrimary,
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
  },
  mapWrap: {
    height: 220,
    marginHorizontal: spacing.lg,
    marginTop: spacing.md,
    borderRadius: radius.md,
    overflow: "hidden",
    backgroundColor: colors.surfaceTertiary,
    borderWidth: 1,
    borderColor: colors.border,
  },
  mapLegend: {
    position: "absolute",
    bottom: spacing.sm,
    left: spacing.sm,
    flexDirection: "row",
    gap: spacing.sm,
    backgroundColor: "rgba(255,255,255,0.9)",
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: radius.pill,
  },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 4 },
  legendDot: { width: 10, height: 10, borderRadius: 5 },
  legendText: { color: colors.onSurface, fontSize: 10, fontWeight: "600" },
  form: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
    gap: spacing.sm,
    marginBottom: spacing.lg,
  },
  formTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.xs },
  gpsRow: { flexDirection: "row", gap: spacing.sm, alignItems: "center" },
  input: {
    backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.md,
    padding: spacing.md,
    color: colors.onSurface,
    borderWidth: 1,
    borderColor: colors.border,
    fontSize: 14,
  },
  gpsBtn: {
    backgroundColor: colors.brandPrimary,
    width: 44,
    height: 44,
    borderRadius: radius.md,
    alignItems: "center",
    justifyContent: "center",
  },
  pickerBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs,
    backgroundColor: colors.brandTertiary,
    padding: spacing.sm,
    borderRadius: radius.md,
    alignSelf: "flex-start",
  },
  pickerBtnText: { color: colors.onBrandTertiary, fontWeight: "700", fontSize: 12 },
  pickerList: {
    backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    maxHeight: 200,
  },
  pickerItem: {
    padding: spacing.sm,
    borderBottomWidth: 0.5,
    borderBottomColor: colors.divider,
  },
  pickerName: { color: colors.onSurface, fontWeight: "700", fontSize: 13 },
  pickerMeta: { color: colors.muted, fontSize: 11, marginTop: 2 },
  primaryBtn: {
    marginTop: spacing.sm,
    backgroundColor: colors.brandPrimary,
    padding: spacing.md,
    borderRadius: radius.md,
    alignItems: "center",
  },
  primaryBtnText: { color: colors.onBrandPrimary, fontWeight: "700" },
  empty: {
    padding: spacing.xxl,
    alignItems: "center",
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  emptyText: { fontWeight: "700", color: colors.onSurface, marginTop: spacing.sm },
  emptySub: { color: colors.muted, fontSize: 12, marginTop: spacing.xs },
  visitCard: {
    flexDirection: "row",
    gap: spacing.md,
    padding: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.sm,
    alignItems: "flex-start",
  },
  pin: {
    width: 36,
    height: 36,
    borderRadius: radius.md,
    backgroundColor: colors.brandPrimary,
    alignItems: "center",
    justifyContent: "center",
  },
  visitTitle: { fontWeight: "700", color: colors.onSurface, fontSize: 14 },
  visitCoord: { color: colors.muted, fontSize: 12, marginTop: 2 },
  visitNotes: { color: colors.onSurfaceTertiary, fontSize: 12, marginTop: 4 },
  visitTime: { color: colors.muted, fontSize: 11, marginTop: 4 },
  endBtn: {
    backgroundColor: colors.surfaceTertiary,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
  },
  endBtnText: { color: colors.onSurface, fontWeight: "700", fontSize: 12 },
});
