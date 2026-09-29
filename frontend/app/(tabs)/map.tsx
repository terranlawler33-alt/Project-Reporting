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
  Modal,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Location from "expo-location";
import * as ImagePicker from "expo-image-picker";
import * as Network from "expo-network";
import Ionicons from "@react-native-vector-icons/ionicons";
import * as Haptics from "expo-haptics";
import { useFocusEffect, useRouter } from "expo-router";
import { Image } from "expo-image";
import { api } from "@/src/api";
import { colors, spacing, radius } from "@/src/theme";
import { PaintOpsMap } from "@/src/components/PaintOpsMap";
import { enqueueAction } from "@/src/offline";
import { uploadVisitPhoto, authedPhotoUrl } from "@/src/photos";

export default function MapScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [visits, setVisits] = useState<any[]>([]);
  const [customers, setCustomers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [gpsLoading, setGpsLoading] = useState(false);
  const [showCustomerPicker, setShowCustomerPicker] = useState(false);
  const [pendingPhotos, setPendingPhotos] = useState<string[]>([]);
  const [showProjectPicker, setShowProjectPicker] = useState(false);
  const [selectedVisit, setSelectedVisit] = useState<any | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [form, setForm] = useState({
    latitude: "",
    longitude: "",
    customer_name: "",
    address: "",
    project_code: "",
    notes: "",
  });

  // Group today's visits by project_id → list of "today's projects" for the attach-to-project modal
  const todaysProjects = (() => {
    const byPid = new Map<string, any>();
    for (const v of visits) {
      const pid = v.project_id;
      if (!pid) continue;
      if (!byPid.has(pid)) {
        byPid.set(pid, {
          project_id: pid,
          customer_name: v.customer_name || "Unnamed customer",
          address: v.address || `${v.latitude.toFixed(4)}, ${v.longitude.toFixed(4)}`,
          project_code: v.project_code || null,
          visit_count: 1,
        });
      } else {
        byPid.get(pid).visit_count += 1;
      }
    }
    return Array.from(byPid.values());
  })();

  // Search suggestions: merge customer directory + unique customer names from visits
  const searchSuggestions = (() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return [] as { name: string; sub?: string; source: string }[];
    const seen = new Set<string>();
    const out: { name: string; sub?: string; source: string }[] = [];
    for (const c of customers) {
      const nm: string = c?.name || "";
      if (!nm) continue;
      if (nm.toLowerCase().includes(q) && !seen.has(nm.toLowerCase())) {
        seen.add(nm.toLowerCase());
        out.push({ name: nm, sub: c.address || c.phone || "Directory", source: "directory" });
      }
    }
    for (const v of visits) {
      const nm: string = v?.customer_name || "";
      if (!nm) continue;
      const key = nm.toLowerCase();
      if (key.includes(q) && !seen.has(key)) {
        seen.add(key);
        out.push({
          name: nm,
          sub: v.address || `${v.latitude?.toFixed?.(4)}, ${v.longitude?.toFixed?.(4)}`,
          source: "visit",
        });
      }
    }
    return out.slice(0, 8);
  })();

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
    // If there are existing projects today, open the picker; otherwise create new project directly
    if (todaysProjects.length > 0) {
      setShowProjectPicker(true);
    } else {
      await commitVisit(null); // new project auto-generated by backend
    }
  };

  const commitVisit = async (project_id: string | null) => {
    if (!form.latitude || !form.longitude) return;
    setSaving(true);
    setShowProjectPicker(false);
    try {
      // If joining an existing project, hydrate customer/address/code from that project so the visit inherits
      let inherit: any = {};
      if (project_id) {
        const proj = todaysProjects.find((p) => p.project_id === project_id);
        if (proj) {
          inherit = {
            customer_name: form.customer_name || proj.customer_name,
            address: form.address || proj.address,
            project_code: form.project_code || proj.project_code,
          };
        }
      }
      const payload = {
        latitude: parseFloat(form.latitude),
        longitude: parseFloat(form.longitude),
        customer_name: inherit.customer_name ?? (form.customer_name || null),
        address: inherit.address ?? (form.address || null),
        project_code: inherit.project_code ?? (form.project_code || null),
        notes: form.notes || null,
        project_id: project_id || null,
      };
      let net = { isConnected: true } as any;
      try {
        net = await Network.getNetworkStateAsync();
      } catch {}
      if (!net.isConnected) {
        await enqueueAction("visit", "/visits", payload);
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
      } else {
        const visit = await api.createVisit(payload);
        // Upload any pending photos
        for (const uri of pendingPhotos) {
          try {
            await uploadVisitPhoto(visit.id, uri);
          } catch {}
        }
      }
      setForm({ latitude: "", longitude: "", customer_name: "", address: "", project_code: "", notes: "" });
      setPendingPhotos([]);
      setShowForm(false);
      await load();
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } finally {
      setSaving(false);
    }
  };

  const pickPhoto = async () => {
    try {
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) return;
      const res = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ["images"],
        quality: 0.7,
      });
      if (!res.canceled && res.assets?.[0]?.uri && pendingPhotos.length < 3) {
        setPendingPhotos((p) => [...p, res.assets[0].uri]);
      }
    } catch {}
  };

  const takePhoto = async () => {
    try {
      const perm = await ImagePicker.requestCameraPermissionsAsync();
      if (!perm.granted) return;
      const res = await ImagePicker.launchCameraAsync({
        mediaTypes: ["images"],
        quality: 0.7,
      });
      if (!res.canceled && res.assets?.[0]?.uri && pendingPhotos.length < 3) {
        setPendingPhotos((p) => [...p, res.assets[0].uri]);
      }
    } catch {}
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

      <View style={styles.searchBox}>
        <View style={styles.searchInputWrap}>
          <Ionicons name="search" size={16} color={colors.muted} />
          <TextInput
            testID="customer-search-input"
            value={searchQuery}
            onChangeText={setSearchQuery}
            placeholder="Search customer to open their file…"
            placeholderTextColor={colors.muted}
            style={styles.searchInput}
            autoCorrect={false}
            autoCapitalize="none"
            returnKeyType="search"
            onSubmitEditing={() => {
              if (searchSuggestions.length > 0) {
                const top = searchSuggestions[0];
                setSearchQuery("");
                router.push(`/customer/${encodeURIComponent(top.name)}`);
              }
            }}
          />
          {searchQuery.length > 0 ? (
            <Pressable onPress={() => setSearchQuery("")} testID="customer-search-clear" hitSlop={8}>
              <Ionicons name="close-circle" size={16} color={colors.muted} />
            </Pressable>
          ) : null}
        </View>
        {searchSuggestions.length > 0 ? (
          <View style={styles.searchDropdown} testID="customer-search-dropdown">
            {searchSuggestions.map((s, idx) => (
              <Pressable
                key={`${s.name}-${idx}`}
                testID={`customer-search-suggest-${idx}`}
                onPress={() => {
                  setSearchQuery("");
                  router.push(`/customer/${encodeURIComponent(s.name)}`);
                }}
                style={styles.searchItem}
              >
                <Ionicons
                  name={s.source === "directory" ? "person" : "location"}
                  size={14}
                  color={colors.brandPrimary}
                />
                <View style={{ flex: 1 }}>
                  <Text style={styles.searchName} numberOfLines={1}>{s.name}</Text>
                  {s.sub ? <Text style={styles.searchSub} numberOfLines={1}>{s.sub}</Text> : null}
                </View>
                <Ionicons name="chevron-forward" size={14} color={colors.muted} />
              </Pressable>
            ))}
          </View>
        ) : searchQuery.trim().length > 0 ? (
          <View style={styles.searchDropdown}>
            <Text style={styles.searchEmpty}>No matching customers</Text>
          </View>
        ) : null}
      </View>

      <View style={styles.mapWrap} testID="live-map-container">
        <PaintOpsMap
          visits={visits}
          onMarkerPress={(v) => setSelectedVisit(v)}
        />
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

            <Text style={styles.photosLabel}>
              Photos ({pendingPhotos.length}/3)
            </Text>
            <View style={styles.photosRow}>
              {pendingPhotos.map((uri, idx) => (
                <View key={uri + idx} style={styles.thumbWrap} testID={`pending-photo-${idx}`}>
                  <Image source={{ uri }} style={styles.thumb} contentFit="cover" />
                  <Pressable
                    testID={`remove-photo-${idx}`}
                    onPress={() => setPendingPhotos((p) => p.filter((_, i) => i !== idx))}
                    style={styles.thumbRemove}
                  >
                    <Ionicons name="close" size={12} color="#fff" />
                  </Pressable>
                </View>
              ))}
              {pendingPhotos.length < 3 && (
                <>
                  <Pressable testID="visit-take-photo" onPress={takePhoto} style={styles.photoBtn}>
                    <Ionicons name="camera" size={20} color={colors.brandPrimary} />
                    <Text style={styles.photoBtnText}>Camera</Text>
                  </Pressable>
                  <Pressable testID="visit-pick-photo" onPress={pickPhoto} style={styles.photoBtn}>
                    <Ionicons name="images" size={20} color={colors.brandPrimary} />
                    <Text style={styles.photoBtnText}>Library</Text>
                  </Pressable>
                </>
              )}
            </View>

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
                {v.photos?.length ? (
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: spacing.xs }}>
                    <View style={{ flexDirection: "row", gap: 4 }}>
                      {v.photos.map((p: string, i: number) => (
                        <VisitPhoto key={p + i} path={p} testID={`visit-photo-${v.id}-${i}`} />
                      ))}
                    </View>
                  </ScrollView>
                ) : null}
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

      {/* Attach-to-Project modal — shown after Save Visit when today already has projects */}
      <Modal
        visible={showProjectPicker}
        transparent
        animationType="slide"
        onRequestClose={() => setShowProjectPicker(false)}
      >
        <View style={styles.modalBackdrop}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Attach pin to which project?</Text>
              <Pressable onPress={() => setShowProjectPicker(false)} testID="project-picker-close">
                <Ionicons name="close" size={22} color={colors.onSurface} />
              </Pressable>
            </View>
            <Text style={styles.modalHint}>
              Choose an existing project from today or start a new one for this pin drop.
            </Text>
            <ScrollView style={{ maxHeight: 320 }}>
              {todaysProjects.map((p) => (
                <Pressable
                  key={p.project_id}
                  testID={`attach-to-${p.project_id}`}
                  onPress={() => commitVisit(p.project_id)}
                  style={styles.projectPickItem}
                >
                  <View style={styles.projectPickIcon}>
                    <Ionicons name="briefcase" size={16} color={colors.onBrandPrimary} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.projectPickTitle} numberOfLines={1}>
                      {p.customer_name}
                      {p.project_code ? ` · ${p.project_code}` : ""}
                    </Text>
                    <Text style={styles.projectPickSub} numberOfLines={1}>
                      {p.address}
                    </Text>
                    <Text style={styles.projectPickCount}>
                      {p.visit_count} pin drop{p.visit_count === 1 ? "" : "s"}
                    </Text>
                  </View>
                  <Ionicons name="chevron-forward" size={18} color={colors.muted} />
                </Pressable>
              ))}
            </ScrollView>
            <Pressable
              testID="attach-to-new-project"
              onPress={() => commitVisit(null)}
              style={styles.newProjectBtn}
            >
              <Ionicons name="add-circle" size={18} color={colors.onBrandPrimary} />
              <Text style={styles.newProjectBtnText}>Start a new project</Text>
            </Pressable>
          </View>
        </View>
      </Modal>

      {/* Pin-tap visit detail sheet with "See customer history" link */}
      <Modal
        visible={!!selectedVisit}
        transparent
        animationType="slide"
        onRequestClose={() => setSelectedVisit(null)}
      >
        <View style={styles.modalBackdrop}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>
                {selectedVisit?.customer_name || "Job Site"}
              </Text>
              <Pressable onPress={() => setSelectedVisit(null)} testID="visit-detail-close">
                <Ionicons name="close" size={22} color={colors.onSurface} />
              </Pressable>
            </View>
            {selectedVisit ? (
              <ScrollView contentContainerStyle={{ paddingBottom: spacing.md }}>
                <View style={styles.detailRow}>
                  <Ionicons name="location" size={14} color={colors.brandPrimary} />
                  <Text style={styles.detailText}>
                    {selectedVisit.address ||
                      `${selectedVisit.latitude.toFixed(5)}, ${selectedVisit.longitude.toFixed(5)}`}
                  </Text>
                </View>
                {selectedVisit.project_code ? (
                  <View style={styles.detailRow}>
                    <Ionicons name="briefcase" size={14} color={colors.brandPrimary} />
                    <Text style={styles.detailText}>{selectedVisit.project_code}</Text>
                  </View>
                ) : null}
                <View style={styles.detailRow}>
                  <Ionicons name="time" size={14} color={colors.brandPrimary} />
                  <Text style={styles.detailText}>
                    {new Date(selectedVisit.timestamp).toLocaleTimeString()}
                    {selectedVisit.ended_at
                      ? ` → ${new Date(selectedVisit.ended_at).toLocaleTimeString()}`
                      : " · still active"}
                  </Text>
                </View>
                {selectedVisit.notes ? (
                  <View style={[styles.detailRow, { alignItems: "flex-start" }]}>
                    <Ionicons name="document-text" size={14} color={colors.brandPrimary} />
                    <Text style={styles.detailText}>{selectedVisit.notes}</Text>
                  </View>
                ) : null}
                {selectedVisit.weather ? (
                  <View style={styles.weatherCard} testID="visit-weather-card">
                    <View style={styles.weatherHeader}>
                      <Ionicons name="partly-sunny" size={16} color={colors.brandPrimary} />
                      <Text style={styles.weatherHeaderText}>
                        {selectedVisit.weather.conditions} · {Math.round(selectedVisit.weather.temperature_f)}°F
                      </Text>
                      <Pressable
                        testID="visit-weather-refresh"
                        onPress={async () => {
                          try {
                            const updated = await api.refreshVisitWeather(selectedVisit.id);
                            setSelectedVisit(updated);
                            await load();
                          } catch {}
                        }}
                        hitSlop={8}
                      >
                        <Ionicons name="refresh" size={14} color={colors.brandPrimary} />
                      </Pressable>
                    </View>
                    <Text style={styles.weatherSub}>
                      Wind {Math.round(selectedVisit.weather.wind_mph || 0)} mph · Precip{" "}
                      {(selectedVisit.weather.precipitation || 0).toFixed(2)} in
                    </Text>
                    {selectedVisit.weather_refreshed_at ? (
                      <Text style={styles.weatherStamp}>
                        Updated {new Date(selectedVisit.weather_refreshed_at).toLocaleTimeString()}
                      </Text>
                    ) : null}
                  </View>
                ) : null}
                {selectedVisit.photos?.length ? (
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: spacing.sm }}>
                    <View style={{ flexDirection: "row", gap: 6 }}>
                      {selectedVisit.photos.map((p: string, i: number) => (
                        <VisitPhoto key={p + i} path={p} testID={`sheet-photo-${i}`} />
                      ))}
                    </View>
                  </ScrollView>
                ) : null}

                {selectedVisit.customer_name ? (
                  <Pressable
                    testID="see-customer-history"
                    onPress={() => {
                      const name = selectedVisit.customer_name;
                      setSelectedVisit(null);
                      router.push(`/customer/${encodeURIComponent(name)}`);
                    }}
                    style={styles.historyBtn}
                  >
                    <Ionicons name="folder-open" size={18} color={colors.onBrandPrimary} />
                    <Text style={styles.historyBtnText}>
                      See customer history →
                    </Text>
                  </Pressable>
                ) : (
                  <Text style={styles.historyMuted}>
                    Add a customer name to this visit to open the customer file.
                  </Text>
                )}
              </ScrollView>
            ) : null}
          </View>
        </View>
      </Modal>
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
  searchBox: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    zIndex: 20,
  },
  searchInputWrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
  },
  searchInput: {
    flex: 1,
    color: colors.onSurface,
    fontSize: 13,
    padding: 0,
  },
  searchDropdown: {
    marginTop: 4,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: 4,
    // shadow for float feel
    shadowColor: "#000",
    shadowOpacity: 0.08,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 4 },
    elevation: 4,
  },
  searchItem: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    padding: spacing.sm,
    borderRadius: radius.sm,
  },
  searchName: { color: colors.onSurface, fontWeight: "700", fontSize: 13 },
  searchSub: { color: colors.muted, fontSize: 11, marginTop: 1 },
  searchEmpty: {
    color: colors.muted,
    fontSize: 12,
    padding: spacing.sm,
    fontStyle: "italic",
    textAlign: "center",
  },
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
  photosLabel: { color: colors.onSurfaceTertiary, fontSize: 12, fontWeight: "700", marginTop: spacing.sm },
  photosRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  thumbWrap: { width: 72, height: 72, borderRadius: radius.md, overflow: "hidden", position: "relative" },
  thumb: { width: "100%", height: "100%" },
  thumbRemove: {
    position: "absolute",
    top: 2,
    right: 2,
    backgroundColor: "rgba(0,0,0,0.6)",
    borderRadius: 10,
    width: 20,
    height: 20,
    alignItems: "center",
    justifyContent: "center",
  },
  photoBtn: {
    width: 72,
    height: 72,
    borderRadius: radius.md,
    backgroundColor: colors.brandTertiary,
    alignItems: "center",
    justifyContent: "center",
    gap: 2,
  },
  photoBtnText: { color: colors.onBrandTertiary, fontSize: 10, fontWeight: "700" },
  modalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.5)",
    justifyContent: "flex-end",
  },
  modalSheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: spacing.lg,
    paddingBottom: spacing.xxl,
    maxHeight: "85%",
  },
  modalHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: spacing.sm,
  },
  modalTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface, flex: 1 },
  modalHint: { color: colors.muted, fontSize: 12, marginBottom: spacing.md, lineHeight: 16 },
  projectPickItem: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    padding: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.xs,
  },
  projectPickIcon: {
    width: 36,
    height: 36,
    borderRadius: radius.md,
    backgroundColor: colors.brandPrimary,
    alignItems: "center",
    justifyContent: "center",
  },
  projectPickTitle: { color: colors.onSurface, fontWeight: "700", fontSize: 14 },
  projectPickSub: { color: colors.muted, fontSize: 12, marginTop: 2 },
  projectPickCount: { color: colors.brandPrimary, fontSize: 11, marginTop: 2, fontWeight: "700" },
  newProjectBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    marginTop: spacing.md,
    padding: spacing.md,
    backgroundColor: colors.brandPrimary,
    borderRadius: radius.md,
  },
  newProjectBtnText: { color: colors.onBrandPrimary, fontWeight: "800", fontSize: 14 },
  detailRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: spacing.xs,
  },
  detailText: { color: colors.onSurface, fontSize: 13, flex: 1 },
  historyBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    marginTop: spacing.lg,
    padding: spacing.md,
    backgroundColor: colors.brandPrimary,
    borderRadius: radius.md,
  },
  historyBtnText: { color: colors.onBrandPrimary, fontWeight: "800", fontSize: 14 },
  historyMuted: {
    color: colors.muted,
    fontSize: 12,
    fontStyle: "italic",
    marginTop: spacing.md,
    textAlign: "center",
  },
  weatherCard: {
    marginTop: spacing.md,
    padding: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  weatherHeader: { flexDirection: "row", alignItems: "center", gap: 6 },
  weatherHeaderText: { flex: 1, color: colors.onSurface, fontSize: 13, fontWeight: "700" },
  weatherSub: { color: colors.muted, fontSize: 12, marginTop: 4 },
  weatherStamp: { color: colors.muted, fontSize: 10, marginTop: 4, fontStyle: "italic" },
});

function VisitPhoto({ path, testID }: { path: string; testID: string }) {
  const [uri, setUri] = useState<string | null>(null);
  useEffect(() => {
    authedPhotoUrl(path).then(setUri);
  }, [path]);
  if (!uri) {
    return <View style={{ width: 60, height: 60, borderRadius: 8, backgroundColor: colors.surfaceTertiary }} testID={testID} />;
  }
  return (
    <Image
      testID={testID}
      source={{ uri }}
      style={{ width: 60, height: 60, borderRadius: 8 }}
      contentFit="cover"
    />
  );
}
