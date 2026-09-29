import { useEffect, useState, useCallback } from "react";
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ScrollView,
  TextInput,
  Modal,
  ActivityIndicator,
  Alert,
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import Ionicons from "@react-native-vector-icons/ionicons";
import * as Location from "expo-location";
import { LinearGradient } from "expo-linear-gradient";
import { Image } from "expo-image";
import { api } from "@/src/api";
import { colors, spacing, radius } from "@/src/theme";

const STORAGE_KEY = "paintops.weather.locations.v1";
const HERO_IMG =
  "https://images.unsplash.com/photo-1505533542167-8c89838bb19e?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA2MjJ8MHwxfHNlYXJjaHwxfHxhYnN0cmFjdCUyMG1vcm5pbmclMjBsaWdodCUyMHNreSUyMHdlYXRoZXIlMjBiYWNrZ3JvdW5kfGVufDB8fHx8MTc5MDY1MTk5NHww&ixlib=rb-4.1.0&q=85";

export type SavedLocation = {
  id: string;
  label: string;
  latitude: number;
  longitude: number;
  is_current?: boolean; // marker only — recomputed at runtime
};

const CURRENT_ID = "__current__";

async function loadLocations(): Promise<SavedLocation[]> {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}
async function saveLocations(locs: SavedLocation[]) {
  try {
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(locs));
  } catch {}
}

function iconForCode(code?: number): any {
  const c = code ?? 0;
  if ([0, 1].includes(c)) return "sunny";
  if ([2, 3].includes(c)) return "partly-sunny";
  if ([45, 48].includes(c)) return "cloudy";
  if ([51, 53, 55, 61, 63, 65, 80, 81, 82].includes(c)) return "rainy";
  if ([71, 73, 75].includes(c)) return "snow";
  if ([95, 96, 99].includes(c)) return "thunderstorm";
  return "partly-sunny";
}

type Props = {
  greetingName: string;
  topPadding: number;
};

export function MultiLocationWeather({ greetingName, topPadding }: Props) {
  const [saved, setSaved] = useState<SavedLocation[]>([]);
  const [snapshots, setSnapshots] = useState<Record<string, any>>({});
  const [loadingIds, setLoadingIds] = useState<Set<string>>(new Set());
  const [activeIdx, setActiveIdx] = useState(0);
  const [showAddModal, setShowAddModal] = useState(false);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [searching, setSearching] = useState(false);
  const [currentCoords, setCurrentCoords] = useState<{ lat: number; lon: number } | null>(null);

  // Build the ordered list: Current GPS first (always present) + saved locations
  const locations: SavedLocation[] = [
    { id: CURRENT_ID, label: "Current location", latitude: 0, longitude: 0, is_current: true },
    ...saved,
  ];

  const fetchWeatherFor = useCallback(async (loc: SavedLocation) => {
    setLoadingIds((prev) => new Set(prev).add(loc.id));
    try {
      let lat = loc.latitude;
      let lon = loc.longitude;
      if (loc.is_current) {
        if (!currentCoords) {
          try {
            const { status } = await Location.requestForegroundPermissionsAsync();
            if (status !== "granted") {
              // fallback to a default coord
              lat = 40.7128; lon = -74.006;
            } else {
              const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
              lat = pos.coords.latitude;
              lon = pos.coords.longitude;
              setCurrentCoords({ lat, lon });
            }
          } catch {
            lat = 40.7128; lon = -74.006;
          }
        } else {
          lat = currentCoords.lat;
          lon = currentCoords.lon;
        }
      }
      const w = await api.weather(lat, lon);
      setSnapshots((prev) => ({ ...prev, [loc.id]: w }));
    } catch {
      // ignore; render "unavailable"
    } finally {
      setLoadingIds((prev) => {
        const s = new Set(prev);
        s.delete(loc.id);
        return s;
      });
    }
  }, [currentCoords]);

  const loadAll = useCallback(async () => {
    const list = await loadLocations();
    setSaved(list);
    // Fetch weather for current + each saved location in parallel
    const all: SavedLocation[] = [
      { id: CURRENT_ID, label: "Current location", latitude: 0, longitude: 0, is_current: true },
      ...list,
    ];
    all.forEach((l) => void fetchWeatherFor(l));
  }, [fetchWeatherFor]);

  useEffect(() => {
    void loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Debounced geocoding search
  useEffect(() => {
    if (!showAddModal) return;
    const q = query.trim();
    if (q.length < 2) {
      setSearchResults([]);
      return;
    }
    let cancelled = false;
    setSearching(true);
    const t = setTimeout(async () => {
      try {
        const r = await api.geocode(q);
        if (!cancelled) setSearchResults(r.results || []);
      } catch {
        if (!cancelled) setSearchResults([]);
      } finally {
        if (!cancelled) setSearching(false);
      }
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [query, showAddModal]);

  const addLocation = async (r: any) => {
    // dedupe by lat/lon
    const exists = saved.some(
      (s) => Math.abs(s.latitude - r.latitude) < 0.0001 && Math.abs(s.longitude - r.longitude) < 0.0001,
    );
    if (exists) {
      Alert.alert("Already saved", "This location is already in your list.");
      return;
    }
    const next: SavedLocation = {
      id: `loc-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      label: r.label || r.name,
      latitude: r.latitude,
      longitude: r.longitude,
    };
    const list = [...saved, next];
    setSaved(list);
    await saveLocations(list);
    setActiveIdx(list.length); // navigate to the newly added card (index = current + saved)
    setShowAddModal(false);
    setQuery("");
    setSearchResults([]);
    await fetchWeatherFor(next);
  };

  const removeLocation = async (id: string) => {
    if (id === CURRENT_ID) return;
    const list = saved.filter((s) => s.id !== id);
    setSaved(list);
    await saveLocations(list);
    setActiveIdx(0);
  };

  const active = locations[activeIdx] || locations[0];
  const weather = snapshots[active.id];
  const isLoading = loadingIds.has(active.id);

  const goPrev = () => setActiveIdx((i) => Math.max(0, i - 1));
  const goNext = () => setActiveIdx((i) => Math.min(locations.length - 1, i + 1));

  return (
    <View style={[styles.hero, { paddingTop: topPadding + spacing.lg }]}>
      <Image source={{ uri: HERO_IMG }} style={StyleSheet.absoluteFill} contentFit="cover" />
      <LinearGradient
        colors={["rgba(17,24,39,0.15)", "rgba(17,24,39,0.75)"]}
        style={StyleSheet.absoluteFill}
      />

      <View style={styles.heroInner}>
        <View style={styles.topRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.greeting}>Good day,</Text>
            <Text style={styles.name} testID="home-user-name">{greetingName}</Text>
          </View>
          <Pressable
            testID="weather-add-location"
            onPress={() => setShowAddModal(true)}
            style={styles.addBtn}
          >
            <Ionicons name="add" size={18} color="#fff" />
          </Pressable>
        </View>

        <View style={styles.weatherRow}>
          <Pressable
            testID="weather-prev"
            onPress={goPrev}
            disabled={activeIdx === 0}
            style={[styles.navArrow, activeIdx === 0 && { opacity: 0.3 }]}
            hitSlop={8}
          >
            <Ionicons name="chevron-back" size={22} color="#fff" />
          </Pressable>

          <View style={styles.weatherBody} testID="weather-card">
            <View style={styles.labelRow}>
              <Ionicons
                name={active.is_current ? "locate" : "location"}
                size={12}
                color="rgba(255,255,255,0.85)"
              />
              <Text style={styles.locLabel} numberOfLines={1}>{active.label}</Text>
              {!active.is_current ? (
                <Pressable
                  testID="weather-remove-location"
                  onPress={() => removeLocation(active.id)}
                  hitSlop={8}
                >
                  <Ionicons name="close-circle" size={14} color="rgba(255,255,255,0.7)" />
                </Pressable>
              ) : null}
            </View>
            {isLoading && !weather ? (
              <ActivityIndicator color="#fff" style={{ marginTop: spacing.md }} />
            ) : weather ? (
              <View style={styles.weatherContent}>
                <Ionicons name={iconForCode(weather.weather_code)} size={30} color="#fff" />
                <Text style={styles.temp} testID="home-weather-temp">
                  {Math.round(weather.temperature_f)}°F
                </Text>
                <View style={{ flex: 1 }}>
                  <Text style={styles.cond}>{weather.conditions}</Text>
                  <Text style={styles.sub}>
                    Wind {Math.round(weather.wind_mph || 0)} mph · Precip{" "}
                    {(weather.precipitation || 0).toFixed(2)} in
                  </Text>
                </View>
              </View>
            ) : (
              <Text style={styles.cond}>Weather unavailable</Text>
            )}
          </View>

          <Pressable
            testID="weather-next"
            onPress={goNext}
            disabled={activeIdx === locations.length - 1}
            style={[styles.navArrow, activeIdx === locations.length - 1 && { opacity: 0.3 }]}
            hitSlop={8}
          >
            <Ionicons name="chevron-forward" size={22} color="#fff" />
          </Pressable>
        </View>

        {/* Pagination dots */}
        <View style={styles.dotsRow}>
          {locations.map((loc, i) => (
            <Pressable
              key={loc.id}
              testID={`weather-dot-${i}`}
              onPress={() => setActiveIdx(i)}
              hitSlop={6}
              style={[
                styles.dot,
                i === activeIdx && styles.dotActive,
              ]}
            />
          ))}
        </View>
      </View>

      {/* Search modal */}
      <Modal
        visible={showAddModal}
        transparent
        animationType="slide"
        onRequestClose={() => setShowAddModal(false)}
      >
        <View style={styles.modalBackdrop}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Add work area weather</Text>
              <Pressable onPress={() => setShowAddModal(false)} testID="weather-modal-close">
                <Ionicons name="close" size={22} color={colors.onSurface} />
              </Pressable>
            </View>
            <View style={styles.searchWrap}>
              <Ionicons name="search" size={16} color={colors.muted} />
              <TextInput
                testID="weather-search-input"
                value={query}
                onChangeText={setQuery}
                placeholder="City, address, or ZIP code"
                placeholderTextColor={colors.muted}
                style={styles.searchInput}
                autoCorrect={false}
                autoCapitalize="words"
              />
              {searching ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : null}
            </View>
            <ScrollView style={{ maxHeight: 380 }}>
              {searchResults.length === 0 && query.trim().length >= 2 && !searching ? (
                <Text style={styles.emptyResults}>No matches.</Text>
              ) : null}
              {searchResults.map((r, i) => (
                <Pressable
                  key={`${r.id}-${i}`}
                  testID={`weather-result-${i}`}
                  onPress={() => addLocation(r)}
                  style={styles.resultItem}
                >
                  <Ionicons name="location" size={16} color={colors.brandPrimary} />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.resultLabel}>{r.label || r.name}</Text>
                    <Text style={styles.resultSub}>
                      {r.latitude.toFixed(3)}, {r.longitude.toFixed(3)}
                      {r.postcodes?.length ? ` · ${r.postcodes[0]}` : ""}
                    </Text>
                  </View>
                  <Ionicons name="add-circle" size={22} color={colors.brandPrimary} />
                </Pressable>
              ))}
            </ScrollView>
            <Text style={styles.hint}>
              Add every jobsite you work at — the weather at each will appear in your daily reports.
            </Text>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  hero: {
    minHeight: 220,
    paddingBottom: spacing.lg,
    borderBottomLeftRadius: radius.xl,
    borderBottomRightRadius: radius.xl,
    overflow: "hidden",
  },
  heroInner: {
    paddingHorizontal: spacing.lg,
    zIndex: 2,
  },
  topRow: {
    flexDirection: "row",
    alignItems: "center",
  },
  greeting: { color: "rgba(255,255,255,0.85)", fontSize: 13 },
  name: { color: "#fff", fontSize: 24, fontWeight: "800", marginBottom: spacing.md },
  addBtn: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: "rgba(255,255,255,0.2)",
    alignItems: "center",
    justifyContent: "center",
  },
  weatherRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
  },
  navArrow: {
    width: 30,
    height: 30,
    alignItems: "center",
    justifyContent: "center",
  },
  weatherBody: { flex: 1, minHeight: 74 },
  labelRow: { flexDirection: "row", alignItems: "center", gap: 4, marginBottom: 4 },
  locLabel: { color: "rgba(255,255,255,0.9)", fontSize: 12, fontWeight: "700", flex: 1 },
  weatherContent: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  temp: { color: "#fff", fontSize: 30, fontWeight: "800" },
  cond: { color: "#fff", fontSize: 14, fontWeight: "700" },
  sub: { color: "rgba(255,255,255,0.75)", fontSize: 11 },
  dotsRow: {
    flexDirection: "row",
    justifyContent: "center",
    gap: 6,
    marginTop: spacing.md,
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: "rgba(255,255,255,0.35)",
  },
  dotActive: { backgroundColor: "#fff", width: 16 },
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
    marginBottom: spacing.md,
  },
  modalTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface, flex: 1 },
  searchWrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    marginBottom: spacing.md,
  },
  searchInput: { flex: 1, color: colors.onSurface, fontSize: 14, padding: 0 },
  emptyResults: {
    color: colors.muted,
    fontSize: 12,
    padding: spacing.md,
    textAlign: "center",
    fontStyle: "italic",
  },
  resultItem: {
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
  resultLabel: { color: colors.onSurface, fontWeight: "700", fontSize: 13 },
  resultSub: { color: colors.muted, fontSize: 11, marginTop: 2 },
  hint: {
    color: colors.muted,
    fontSize: 11,
    marginTop: spacing.md,
    fontStyle: "italic",
    textAlign: "center",
  },
});
