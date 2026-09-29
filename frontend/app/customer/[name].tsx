import { useEffect, useState } from "react";
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  Pressable,
  ActivityIndicator,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import { Image } from "expo-image";
import { api } from "@/src/api";
import { authedPhotoUrl } from "@/src/photos";
import { colors, spacing, radius } from "@/src/theme";

export default function CustomerHistory() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { name: rawName } = useLocalSearchParams<{ name: string }>();
  const name = decodeURIComponent(rawName || "");
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!name) return;
    (async () => {
      try {
        const res = await api.customerHistory(name);
        setData(res);
      } catch (e: any) {
        setError(e.message || "Failed to load customer file");
      } finally {
        setLoading(false);
      }
    })();
  }, [name]);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.brandPrimary} />
      </View>
    );
  }
  if (error) {
    return (
      <View style={styles.center}>
        <Text style={{ color: colors.error }}>{error}</Text>
      </View>
    );
  }

  const customer = data?.customer;
  const visits: any[] = data?.visits || [];
  const reports: any[] = data?.reports || [];
  const photos: any[] = data?.photos || [];

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} testID="customer-history-back">
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <View style={{ flex: 1, marginLeft: spacing.sm }}>
          <Text style={styles.headerTitle} numberOfLines={1}>
            {name}
          </Text>
          <Text style={styles.headerSub}>Customer file</Text>
        </View>
      </View>

      <ScrollView
        contentContainerStyle={{
          padding: spacing.lg,
          paddingBottom: (insets.bottom || 0) + spacing.xl,
        }}
      >
        <View style={styles.statsRow}>
          <Stat label="Visits" value={data?.counts?.visits ?? 0} />
          <Stat label="Reports" value={data?.counts?.reports ?? 0} />
          <Stat label="Photos" value={data?.counts?.photos ?? 0} />
        </View>

        {customer ? (
          <View style={styles.card} testID="customer-info">
            <Text style={styles.cardHeader}>Contact info</Text>
            {customer.address ? (
              <Row icon="location" text={customer.address} />
            ) : null}
            {customer.phone ? <Row icon="call" text={customer.phone} /> : null}
            {customer.email ? <Row icon="mail" text={customer.email} /> : null}
            {customer.project_code ? (
              <Row icon="briefcase" text={customer.project_code} />
            ) : null}
            {customer.notes ? (
              <Text style={styles.notes}>{customer.notes}</Text>
            ) : null}
          </View>
        ) : (
          <View style={styles.card}>
            <Text style={styles.cardHeader}>Not in directory</Text>
            <Text style={styles.muted}>
              This customer isn't saved in the directory yet. Only visits + report history are shown below.
            </Text>
          </View>
        )}

        <Text style={styles.sectionTitle}>Recent visits ({visits.length})</Text>
        {visits.length === 0 ? (
          <Text style={styles.muted}>No visits logged for this customer.</Text>
        ) : (
          visits.map((v) => (
            <View key={v.id} style={styles.visitRow} testID={`history-visit-${v.id}`}>
              <View style={styles.pin}>
                <Ionicons name="location" size={14} color={colors.onBrandPrimary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.visitTitle}>
                  {v.address ||
                    `${v.latitude?.toFixed?.(4)}, ${v.longitude?.toFixed?.(4)}`}
                </Text>
                <Text style={styles.visitMeta}>
                  {new Date(v.timestamp).toLocaleString()}
                  {v.project_code ? ` · ${v.project_code}` : ""}
                </Text>
                {v.notes ? <Text style={styles.visitNotes}>{v.notes}</Text> : null}
              </View>
            </View>
          ))
        )}

        <Text style={styles.sectionTitle}>Reports mentioning this customer ({reports.length})</Text>
        {reports.length === 0 ? (
          <Text style={styles.muted}>No reports yet.</Text>
        ) : (
          reports.map((r) => (
            <Pressable
              key={r.id}
              testID={`history-report-${r.id}`}
              onPress={() => router.push(`/report/${r.id}`)}
              style={styles.reportRow}
            >
              <View style={{ flex: 1 }}>
                <Text style={styles.reportTitle}>
                  {r.report_date} · {r.author_name}
                </Text>
                <Text style={styles.reportMeta}>{r.author_role}</Text>
              </View>
              {r.priority_level ? (
                <View style={[styles.priorityChip, priorityStyle(r.priority_level)]}>
                  <Text style={styles.priorityChipText}>{r.priority_level.toUpperCase()}</Text>
                </View>
              ) : null}
              <Ionicons name="chevron-forward" size={18} color={colors.muted} />
            </Pressable>
          ))
        )}

        {photos.length > 0 ? (
          <>
            <Text style={styles.sectionTitle}>Photos ({photos.length})</Text>
            <View style={styles.photosGrid}>
              {photos.map((p, i) => (
                <HistoryPhoto key={p.path + i} path={p.path} />
              ))}
            </View>
          </>
        ) : null}
      </ScrollView>
    </View>
  );
}

function priorityStyle(level: string) {
  switch (level) {
    case "High":
      return { backgroundColor: "#DC2626" };
    case "Medium":
      return { backgroundColor: "#D97706" };
    case "Low":
      return { backgroundColor: "#4B5563" };
    default:
      return { backgroundColor: colors.brandPrimary };
  }
}

function Row({ icon, text }: { icon: any; text: string }) {
  return (
    <View style={styles.row}>
      <Ionicons name={icon} size={14} color={colors.brandPrimary} />
      <Text style={styles.rowText}>{text}</Text>
    </View>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

function HistoryPhoto({ path }: { path: string }) {
  const [uri, setUri] = useState<string | null>(null);
  useEffect(() => {
    authedPhotoUrl(path).then(setUri);
  }, [path]);
  if (!uri) {
    return <View style={[styles.photoThumb, { backgroundColor: colors.surfaceTertiary }]} />;
  }
  return <Image source={{ uri }} style={styles.photoThumb} contentFit="cover" />;
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  header: {
    flexDirection: "row",
    alignItems: "flex-end",
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
  },
  headerTitle: { fontSize: 20, fontWeight: "800", color: colors.onSurface },
  headerSub: { color: colors.muted, fontSize: 12, marginTop: 2 },
  statsRow: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.lg },
  stat: {
    flex: 1,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    alignItems: "center",
  },
  statValue: { fontSize: 22, fontWeight: "800", color: colors.brandPrimary },
  statLabel: { fontSize: 11, color: colors.onSurfaceTertiary, marginTop: 2, fontWeight: "700" },
  card: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    marginBottom: spacing.lg,
  },
  cardHeader: {
    fontSize: 12,
    fontWeight: "800",
    color: colors.onSurfaceTertiary,
    textTransform: "uppercase",
    marginBottom: spacing.xs,
  },
  row: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 4 },
  rowText: { color: colors.onSurface, fontSize: 13, flex: 1 },
  notes: { color: colors.muted, fontSize: 12, marginTop: spacing.xs, fontStyle: "italic" },
  muted: { color: colors.muted, fontSize: 12, marginBottom: spacing.md },
  sectionTitle: {
    fontSize: 14,
    fontWeight: "800",
    color: colors.onSurface,
    marginTop: spacing.md,
    marginBottom: spacing.sm,
  },
  visitRow: {
    flexDirection: "row",
    gap: spacing.sm,
    padding: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.xs,
    alignItems: "flex-start",
  },
  pin: {
    width: 28,
    height: 28,
    borderRadius: radius.md,
    backgroundColor: colors.brandPrimary,
    alignItems: "center",
    justifyContent: "center",
  },
  visitTitle: { color: colors.onSurface, fontWeight: "700", fontSize: 13 },
  visitMeta: { color: colors.muted, fontSize: 11, marginTop: 2 },
  visitNotes: { color: colors.onSurfaceTertiary, fontSize: 12, marginTop: 4 },
  reportRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    padding: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.xs,
  },
  reportTitle: { color: colors.onSurface, fontWeight: "700", fontSize: 13 },
  reportMeta: { color: colors.muted, fontSize: 11, marginTop: 2 },
  priorityChip: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radius.pill,
  },
  priorityChipText: { color: "#fff", fontWeight: "800", fontSize: 10 },
  photosGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  photoThumb: { width: 88, height: 88, borderRadius: radius.md },
});
