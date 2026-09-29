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
                    return (
                      <Fragment key={`pt-${i}`}>
                        <Circle
                          cx={cx}
                          cy={cy}
                          r={3.5}
                          fill={colors.brandPrimary}
                        />
                        <SvgText
                          x={cx}
                          y={cy - 8}
                          fill={colors.onSurface}
                          fontSize={10}
                          fontWeight="700"
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
                {points.map((p, i) => (
                  <View key={`row-${i}`} style={styles.row} testID={`hourly-row-${i}`}>
                    <Text style={styles.rowHour}>{p.hour_label}</Text>
                    <Ionicons name={weatherIcon(p.weather_code)} size={18} color={colors.brandPrimary} />
                    <Text style={styles.rowCond} numberOfLines={1}>
                      {p.conditions || "—"}
                    </Text>
                    <View style={styles.rowRight}>
                      <Text style={styles.rowTemp}>
                        {p.temperature_f != null ? `${Math.round(p.temperature_f)}°F` : "—"}
                      </Text>
                      <Text style={styles.rowRain}>
                        💧 {Math.round(p.precip_prob ?? 0)}%
                      </Text>
                    </View>
                  </View>
                ))}
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
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderBottomWidth: 0.5,
    borderBottomColor: colors.divider,
  },
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
