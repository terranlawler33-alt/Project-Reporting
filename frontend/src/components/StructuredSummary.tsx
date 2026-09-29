import { Fragment } from "react";
import { View, Text, StyleSheet } from "react-native";
import { colors, spacing, radius } from "@/src/theme";

const KNOWN_HEADERS = [
  "WORK COMPLETED",
  "COMMUNICATIONS",
  "WEATHER IMPACT",
  "DELAY / CONSTRAINTS",
  "CHANGE ORDER / MATERIALS",
  "NEXT STEPS",
  "OVERALL SUMMARY",
];

type Section = { header: string; lines: string[] };

function parseSections(md: string): Section[] {
  const out: Section[] = [];
  let current: Section | null = null;
  for (const raw of md.split(/\r?\n/)) {
    const line = raw.trim();
    const strippedHeader = line.replace(/^#+/, "").trim().toUpperCase();
    if (line.startsWith("#") && KNOWN_HEADERS.includes(strippedHeader)) {
      if (current) out.push(current);
      current = { header: strippedHeader, lines: [] };
    } else if (current) {
      current.lines.push(line);
    }
  }
  if (current) out.push(current);
  return out;
}

/** Render a bullet: inline **bold** as amber highlight; [URGENT: X] entire line red. */
function renderBullet(text: string, key: string, isUrgent: boolean) {
  const cleaned = text.replace(/^-\s*/, "");
  const parts: React.ReactNode[] = [];
  let i = 0;
  const regex = /\*\*(.+?)\*\*/g;
  let m: RegExpExecArray | null;
  while ((m = regex.exec(cleaned)) !== null) {
    if (m.index > i) parts.push(<Text key={`t-${key}-${i}`}>{cleaned.slice(i, m.index)}</Text>);
    parts.push(
      <Text key={`b-${key}-${m.index}`} style={styles.highlight}>
        {" "}
        {m[1]}{" "}
      </Text>,
    );
    i = m.index + m[0].length;
  }
  if (i < cleaned.length) parts.push(<Text key={`t-${key}-tail`}>{cleaned.slice(i)}</Text>);
  return (
    <View key={key} style={styles.bulletRow}>
      <Text style={[styles.bulletDot, isUrgent && { color: colors.error }]}>•</Text>
      <Text style={[styles.bulletText, isUrgent && styles.urgentText]}>
        {parts.length ? parts : cleaned}
      </Text>
    </View>
  );
}

export function StructuredSummary({ summary }: { summary: string }) {
  const sections = parseSections(summary);
  if (sections.length === 0) {
    // Fallback: raw text if AI didn't return the expected structure
    return <Text style={styles.raw}>{summary}</Text>;
  }
  return (
    <View>
      {sections.map((sec, idx) => {
        const bullets = sec.lines.filter((l) => l.startsWith("-") || l.startsWith("[URGENT:"));
        const paragraphs = sec.lines.filter(
          (l) => l && !l.startsWith("-") && !l.startsWith("[URGENT:"),
        );
        return (
          <View key={idx} style={styles.section} testID={`section-${sec.header.replace(/\s|\/|,/g, "-")}`}>
            <Text style={styles.header}>{sec.header}</Text>
            <View style={styles.headerUnderline} />
            {bullets.length === 0 && paragraphs.length === 0 ? (
              <Text style={styles.noneText}>None reported today.</Text>
            ) : (
              <Fragment>
                {bullets.map((b, i) => {
                  const isUrgent = b.toUpperCase().includes("[URGENT:") || b.startsWith("[URGENT:");
                  return renderBullet(b, `${idx}-${i}`, isUrgent);
                })}
                {paragraphs.map((p, i) => (
                  <Text key={`p-${idx}-${i}`} style={styles.paragraph}>
                    {p}
                  </Text>
                ))}
              </Fragment>
            )}
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  raw: { color: colors.onSurface, fontSize: 14, lineHeight: 21 },
  section: { marginBottom: spacing.lg },
  header: {
    color: colors.onSurface,
    fontSize: 13,
    fontWeight: "800",
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  headerUnderline: {
    height: 2,
    width: 60,
    backgroundColor: colors.brandPrimary,
    marginTop: 4,
    marginBottom: spacing.sm,
    borderRadius: 1,
  },
  bulletRow: { flexDirection: "row", gap: 6, marginBottom: 4 },
  bulletDot: { color: colors.brandPrimary, fontSize: 14, lineHeight: 20, fontWeight: "700" },
  bulletText: { flex: 1, color: colors.onSurface, fontSize: 14, lineHeight: 20 },
  urgentText: { color: colors.error, fontWeight: "700" },
  paragraph: { color: colors.onSurface, fontSize: 14, lineHeight: 20, marginTop: 4 },
  noneText: { color: colors.muted, fontStyle: "italic", fontSize: 12 },
  highlight: {
    backgroundColor: "#FEF3C7",
    color: "#92400E",
    fontWeight: "700",
    borderRadius: radius.sm,
    overflow: "hidden",
  },
});
