import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useRouter } from "expo-router";
import { Image } from "expo-image";
import { useAuth } from "@/src/auth/AuthProvider";
import { colors, spacing, radius } from "@/src/theme";

const AVATAR_IMG =
  "https://images.unsplash.com/photo-1646227655685-a530813759b3?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2Nzd8MHwxfHNlYXJjaHwxfHxwcm9mZXNzaW9uYWwlMjBjb25zdHJ1Y3Rpb24lMjB3b3JrZXIlMjBwcm9maWxlJTIwcG9ydHJhaXR8ZW58MHx8fHwxNzkwNjUxOTk0fDA&ixlib=rb-4.1.0&q=85";

export default function ProfileScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user, logout } = useAuth();

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView
        contentContainerStyle={{
          paddingTop: insets.top + spacing.lg,
          paddingBottom: (insets.bottom || 0) + 100,
        }}
      >
        <View style={styles.profileHeader}>
          <Image source={{ uri: AVATAR_IMG }} style={styles.avatar} />
          <Text style={styles.name} testID="profile-name">{user?.name}</Text>
          <Text style={styles.role}>
            {user?.role} {user?.job_title ? `· ${user.job_title}` : ""}
          </Text>
          <Text style={styles.email}>{user?.email}</Text>
        </View>

        <Section title="Data">
          <Row
            testID="sms-log-nav"
            icon="chatbubbles"
            title="Communications Log"
            subtitle="Log calls & texts with subs and customers"
            onPress={() => router.push("/sms-log")}
          />
          <Row
            testID="customers-nav"
            icon="people-circle"
            title="Customer Directory"
            subtitle="Save recurring customers for quick check-ins"
            onPress={() => router.push("/admin/customers")}
          />
        </Section>

        {user?.is_admin && (
          <Section title="Administration">
            <Row
              testID="admin-users-nav"
              icon="people"
              title="Manage Users"
              subtitle="Create roles: Owner, Ops, Sales, Production, Labor, PM"
              onPress={() => router.push("/admin/users")}
            />
            <Row
              testID="admin-groups-nav"
              icon="mail-open"
              title="Recipient Groups"
              subtitle="Save Owners / Ops / Subs to send with one tap"
              onPress={() => router.push("/admin/recipient-groups")}
            />
            <Row
              testID="admin-digest-nav"
              icon="mail-unread"
              title="Weekly Digest"
              subtitle="AI-roll up last 7 days & email the owner"
              onPress={() => router.push("/admin/digest")}
            />
          </Section>
        )}

        <Section title="Account">
          <Row
            testID="settings-lists-nav"
            icon="options"
            title="Custom Lists"
            subtitle="Add, edit or delete break types & priority flags"
            onPress={() => router.push("/profile/settings")}
          />
          <Row
            testID="logout-button"
            icon="log-out"
            title="Sign out"
            danger
            onPress={logout}
          />
        </Section>
      </ScrollView>
    </View>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={{ marginTop: spacing.xl }}>
      <Text style={styles.sectionTitle}>{title}</Text>
      <View style={styles.sectionCard}>{children}</View>
    </View>
  );
}

function Row({
  icon,
  title,
  subtitle,
  onPress,
  danger,
  testID,
}: {
  icon: any;
  title: string;
  subtitle?: string;
  onPress: () => void;
  danger?: boolean;
  testID?: string;
}) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      style={({ pressed }) => [styles.row, pressed && { opacity: 0.7 }]}
    >
      <View style={[styles.rowIcon, danger && { backgroundColor: "#FEE2E2" }]}>
        <Ionicons name={icon} size={18} color={danger ? colors.error : colors.onBrandTertiary} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={[styles.rowTitle, danger && { color: colors.error }]}>{title}</Text>
        {subtitle ? <Text style={styles.rowSub}>{subtitle}</Text> : null}
      </View>
      {!danger && <Ionicons name="chevron-forward" size={16} color={colors.muted} />}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  profileHeader: {
    alignItems: "center",
    paddingHorizontal: spacing.lg,
  },
  avatar: {
    width: 96,
    height: 96,
    borderRadius: 48,
    marginBottom: spacing.md,
    backgroundColor: colors.surfaceTertiary,
  },
  name: { fontSize: 22, fontWeight: "700", color: colors.onSurface },
  role: { color: colors.brandPrimary, fontWeight: "700", marginTop: 2 },
  email: { color: colors.muted, fontSize: 13, marginTop: spacing.xs },
  sectionTitle: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginBottom: spacing.sm,
    marginHorizontal: spacing.lg,
  },
  sectionCard: {
    backgroundColor: colors.surfaceSecondary,
    marginHorizontal: spacing.lg,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: "hidden",
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    padding: spacing.md,
    gap: spacing.md,
    borderBottomWidth: 0.5,
    borderBottomColor: colors.divider,
  },
  rowIcon: {
    width: 36,
    height: 36,
    borderRadius: radius.md,
    backgroundColor: colors.brandTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
  rowTitle: { fontWeight: "700", color: colors.onSurface, fontSize: 14 },
  rowSub: { color: colors.muted, fontSize: 12, marginTop: 2 },
});
