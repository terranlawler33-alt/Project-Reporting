import { useEffect, useState, Fragment } from "react";
import {
  View,
  Text,
  StyleSheet,
  Modal,
  Pressable,
  ActivityIndicator,
  ScrollView,
} from "react-native";
import Svg, { Path, Circle, Line, Rect, Text as SvgText } from "react-native-svg";
import Ionicons from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { colors, spacing } from "@/src/theme";

type HourlyPoint = {
  time: string | null;
  hour_label: string;
  temperature_f: number | null;
  precip_prob: number | null;
  precipitation: number | null;
  wind_mph: number | null;
  weather_code: number | null;
  conditions: string | null;
};

type Props = {
  visible: boolean;
  onClose: () => void;
  latitude: number | null;
  longitude: number | null;
  locationLabel: string;
};

function weatherIcon(code?: number | null): any {
  const c = code ?? 0;
  if ([0, 1].includes(c)) return "sunny";
  if ([2, 3].includes(c)) return "partly-sunny";
  if ([45, 48].includes(c)) return "cloudy";
  if ([51, 53, 55, 61, 63, 65, 80, 81, 82].includes(c)) return "rainy";
  if ([71, 73, 75].includes(c)) return "snow";
  if ([95, 96, 99].includes(c)) return "thunderstorm";
  return "partly-sunny";
}

export function HourlyForecastSheet({
  visible,
  onClose,
  latitude,
  longitude,
  locationLabel,
}: Props) {
  const [points, setPoints] = useState<HourlyPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!visible || latitude == null || longitude == null) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const res = await api.weatherHourly(latitude, longitude, 12);
        if (!cancelled) setPoints(res.points || []);
      } catch (e: any) {
        if (!cancelled) setError(e?.message || "Could not load forecast");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [visible, latitude, longitude]);

  const temps = points.map((p) => p.temperature_f ?? 0);
  const minT = temps.length ? Math.min(...temps) : 0;
  const maxT = temps.length ? Math.max(...temps) : 1;
  const tRange = Math.max(1, maxT - minT);

  // ---------- Best Start Time recommendation ----------
  // Score each hour by warmth + dryness. Weighted 55% temp, 45% low-rain.
  // Wind above 20 mph applies a penalty. Only future hours are considered.
  let bestIdx = -1;
  let bestScore = -Infinity;
  points.forEach((p, i) => {
    const t = p.temperature_f ?? minT;
    const rain = p.precip_prob ?? 0;
    const wind = p.wind_mph ?? 0;
    const tempScore = tRange > 0 ? ((t - minT) / tRange) * 100 : 100;
    const dryScore = 100 - rain;
    const windPenalty = wind > 20 ? Math.min(30, (wind - 20) * 2) : 0;
    const score = tempScore * 0.55 + dryScore * 0.45 - windPenalty;
    if (score > bestScore) {
      bestScore = score;
      bestIdx = i;
    }
  });
  const bestPoint = bestIdx >= 0 ? points[bestIdx] : null;
  const bestReason = (() => {
    if (!bestPoint) return "";
    const rain = bestPoint.precip_prob ?? 0;
    const wind = bestPoint.wind_mph ?? 0;
    if (rain >= 60) return "Wettest day — this is the driest window";
    if (rain <= 10 && (bestPoint.temperature_f ?? 0) >= maxT - 2) return "Warm & dry — ideal to start";
    if (rain <= 20) return "Dry window, near the day's peak temp";
    if (wind > 20) return "Watch wind — best of the low-rain hours";
    return "Best mix of temp + low rain in the next 12h";
  })();

  // Chart geometry
  const chartWidth = Math.max(320, points.length * 44); // ensure horizontal scroll for 12+ points
  const chartHeight = 180;
  const padX = 24;
  const padTop = 30; // space above the curve for temp labels
  const padBottom = 90; // space for rain bars + hour labels

  const xFor = (i: number) =>
    padX + ((chartWidth - 2 * padX) * i) / Math.max(1, points.length - 1);
  const yForTemp = (t: number) => {
    const ratio = (t - minT) / tRange;
    return padTop + (chartHeight - padTop - padBottom) * (1 - ratio);
  };

  // Build the smooth temperature curve as a Path (linear for simplicity)
  const curvePath =
    points.length > 1
      ? points
          .map((p, i) => {
            const cmd = i === 0 ? "M" : "L";
            return `${cmd}${xFor(i).toFixed(1)} ${yForTemp(p.temperature_f ?? minT).toFixed(1)}`;
          })
          .join(" ")
      : "";

  const barMaxHeight = 40;
  const barBottomY = chartHeight - 30; // bottom of bars zone (above hour labels)

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
    >
      <View style={styles.backdrop}>
        <View style={styles.sheet}>
          <View style={styles.header}>
            <View style={{ flex: 1 }}>
              <Text style={styles.title}>Next 12 hours</Text>
              <Text style={styles.subtitle} numberOfLines={1}>
                {locationLabel}
              </Text>
            </View>
            <Pressable onPress={onClose} testID="hourly-close" hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.onSurface} />
            </Pressable>
          </View>

          {loading ? (
            <View style={styles.centerBox}>
              <ActivityIndicator color={colors.brandPrimary} />
              <Text style={styles.hint}>Loading forecast…</Text>
            </View>
          ) : error ? (
            <View style={styles.centerBox}>
              <Ionicons name="alert-circle" size={24} color={colors.error} />
              <Text style={[styles.hint, { color: colors.error }]}>{error}</Text>
            </View>
          ) : points.length === 0 ? (
            <View style={styles.centerBox}>
              <Text style={styles.hint}>No forecast data available.</Text>
            </View>
          ) : (
            <>
              <View style={styles.legendRow}>
                <View style={styles.legendItem}>
                  <View style={[styles.legendSwatch, { backgroundColor: colors.brandPrimary }]} />
                  <Text style={styles.legendText}>Temp (°F)</Text>
                </View>
                <View style={styles.legendItem}>
                  <View style={[styles.legendSwatch, { backgroundColor: "#3B82F6" }]} />
                  <Text style={styles.legendText}>Rain chance</Text>
                </View>
              </View>

              {bestPoint ? (
                <View style={styles.bestChip} testID="hourly-best-chip">
                  <View style={styles.bestBadge}>
                    <Ionicons name="star" size={12} color="#F59E0B" />
                    <Text style={styles.bestBadgeText}>BEST START</Text>
                  </View>
                  <View style={styles.bestBody}>
                    <Text style={styles.bestTime} testID="hourly-best-time">
                      {bestPoint.hour_label}
                    </Text>
                    <Text style={styles.bestMeta}>
                      {bestPoint.temperature_f != null
                        ? `${Math.round(bestPoint.temperature_f)}°F`
                        : "—"}{" "}
                      · 💧 {Math.round(bestPoint.precip_prob ?? 0)}% · 💨{" "}
                      {Math.round(bestPoint.wind_mph ?? 0)} mph
                    </Text>
                    <Text style={styles.bestReason}>{bestReason}</Text>
                  </View>
                </View>
              ) : null}
              <ScrollView
                horizontal
                showsHorizontalScrollIndicator
                contentContainerStyle={{ paddingHorizontal: spacing.md }}
                testID="hourly-scroll"
              >
                <Svg width={chartWidth} height={chartHeight}>
                  {/* Baseline */}
                  <Line
                    x1={padX}
                    y1={barBottomY}
                    x2={chartWidth - padX}
                    y2={barBottomY}
                    stroke={colors.border}
                    strokeWidth={1}
                  />
                  {/* Rain probability bars */}
                  {points.map((p, i) => {
                    const prob = Math.max(0, Math.min(100, p.precip_prob ?? 0));
                    const h = (barMaxHeight * prob) / 100;
                    const x = xFor(i) - 10;
                    return (
                      <Rect
                        key={`bar-${i}`}
                        x={x}
                        y={barBottomY - h}
                        width={20}
                        height={h}
                        fill="#3B82F6"
                        opacity={0.75}
                        rx={3}
                      />
                    );
                  })}
                  {/* Temperature curve */}
                  {curvePath ? (
                    <Path
                      d={curvePath}
                      stroke={colors.brandPrimary}
                      strokeWidth={3}
                      fill="none"
                    />
                  ) : null}
                  {/* Points + temperature labels */}
                  {points.map((p, i) => {
                    const cx = xFor(i);
                    const cy = yForTemp(p.temperature_f ?? minT);
                    const prob = p.precip_prob ?? 0;
                    const isBest = i === bestIdx;
                    return (
                      <Fragment key={`pt-${i}`}>
                        {isBest ? (
                          <Circle
                            cx={cx}
                            cy={cy}
                            r={8}
                            fill="none"
                            stroke="#F59E0B"
                            strokeWidth={2}
                          />
                        ) : null}
                        <Circle
                          cx={cx}
                          cy={cy}
                          r={isBest ? 5 : 3.5}
                          fill={isBest ? "#F59E0B" : colors.brandPrimary}
                        />
                        <SvgText
                          x={cx}
                          y={cy - (isBest ? 12 : 8)}
                          fill={isBest ? "#F59E0B" : colors.onSurface}
                          fontSize={isBest ? 12 : 10}
                          fontWeight="800"
                          textAnchor="middle"
                        >
                          {p.temperature_f != null ? `${Math.round(p.temperature_f)}°` : ""}
                        </SvgText>
                        {/* Rain % label above bar */}
                        {prob > 0 ? (
                          <SvgText
                            x={cx}
                            y={barBottomY - (barMaxHeight * prob) / 100 - 4}
                            fill="#3B82F6"
                            fontSize={9}
                            fontWeight="700"
                            textAnchor="middle"
                          >
                            {Math.round(prob)}%
                          </SvgText>
                        ) : null}
                        {/* Hour label */}
                        <SvgText
                          x={cx}
                          y={chartHeight - 12}
                          fill={colors.muted}
                          fontSize={10}
                          fontWeight="600"
                          textAnchor="middle"
                        >
                          {p.hour_label}
                        </SvgText>
                      </Fragment>
                    );
                  })}
                </Svg>
              </ScrollView>

              {/* Compact hourly list */}
              <ScrollView
                style={{ marginTop: spacing.md, maxHeight: 220 }}
                showsVerticalScrollIndicator
              >
                {points.map((p, i) => {
                  const isBest = i === bestIdx;
                  return (
                    <View
                      key={`row-${i}`}
                      style={[styles.row, isBest && styles.rowBest]}
                      testID={`hourly-row-${i}`}
                    >
                      {isBest ? (
                        <Ionicons name="star" size={12} color="#F59E0B" style={{ position: "absolute", left: 4, top: 12 }} />
                      ) : null}
                      <Text style={[styles.rowHour, isBest && styles.rowBestText]}>{p.hour_label}</Text>
                      <Ionicons name={weatherIcon(p.weather_code)} size={18} color={isBest ? "#F59E0B" : colors.brandPrimary} />
                      <Text style={styles.rowCond} numberOfLines={1}>
                        {p.conditions || "—"}
                      </Text>
                      <View style={styles.rowRight}>
                        <Text style={[styles.rowTemp, isBest && styles.rowBestText]}>
                          {p.temperature_f != null ? `${Math.round(p.temperature_f)}°F` : "—"}
                        </Text>
                        <Text style={styles.rowRain}>
                          💧 {Math.round(p.precip_prob ?? 0)}%
                        </Text>
                      </View>
                    </View>
                  );
                })}
              </ScrollView>

              <Text style={styles.hint}>
                Plan starts around the low-rain windows and warmest hours.
              </Text>
            </>
          )}
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.5)",
    justifyContent: "flex-end",
  },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: spacing.lg,
    paddingBottom: spacing.xxl,
    maxHeight: "92%",
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: spacing.sm,
  },
  title: { fontSize: 17, fontWeight: "800", color: colors.onSurface },
  subtitle: { fontSize: 12, color: colors.muted, marginTop: 2 },
  centerBox: { paddingVertical: spacing.xxl, alignItems: "center", gap: spacing.sm },
  hint: {
    color: colors.muted,
    fontSize: 11,
    marginTop: spacing.md,
    fontStyle: "italic",
    textAlign: "center",
  },
  legendRow: {
    flexDirection: "row",
    justifyContent: "center",
    gap: spacing.lg,
    marginBottom: spacing.xs,
  },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 4 },
  legendSwatch: { width: 12, height: 4, borderRadius: 2 },
  legendText: { color: colors.muted, fontSize: 11, fontWeight: "600" },
  bestChip: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    marginTop: spacing.sm,
    marginBottom: spacing.md,
    marginHorizontal: spacing.md,
    padding: spacing.md,
    backgroundColor: "rgba(245, 158, 11, 0.10)",
    borderWidth: 1,
    borderColor: "rgba(245, 158, 11, 0.55)",
    borderRadius: 12,
  },
  bestBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    backgroundColor: "rgba(245, 158, 11, 0.18)",
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 999,
  },
  bestBadgeText: {
    color: "#B45309",
    fontSize: 10,
    fontWeight: "800",
    letterSpacing: 0.5,
  },
  bestBody: { flex: 1 },
  bestTime: { color: colors.onSurface, fontSize: 18, fontWeight: "800" },
  bestMeta: { color: colors.onSurfaceTertiary, fontSize: 12, marginTop: 2 },
  bestReason: { color: colors.muted, fontSize: 11, marginTop: 2, fontStyle: "italic" },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderBottomWidth: 0.5,
    borderBottomColor: colors.divider,
  },
  rowBest: {
    backgroundColor: "rgba(245, 158, 11, 0.10)",
    borderLeftWidth: 3,
    borderLeftColor: "#F59E0B",
    paddingLeft: spacing.md + 4,
  },
  rowBestText: { color: "#B45309" },
  rowHour: {
    width: 52,
    color: colors.onSurface,
    fontSize: 13,
    fontWeight: "700",
  },
  rowCond: { flex: 1, color: colors.onSurfaceTertiary, fontSize: 12 },
  rowRight: { alignItems: "flex-end" },
  rowTemp: { color: colors.onSurface, fontSize: 13, fontWeight: "800" },
  rowRain: { color: "#3B82F6", fontSize: 11, fontWeight: "700", marginTop: 2 },
});
