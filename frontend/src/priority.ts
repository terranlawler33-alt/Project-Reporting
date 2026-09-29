export const PRIORITY_LEVELS = ["High", "Medium", "Low"] as const;
export type PriorityLevel = (typeof PRIORITY_LEVELS)[number];

export type PriorityFlagDef = {
  type: string;
  requiresReason: boolean;
};

// Order matches the product spec provided by the user.
export const PRIORITY_FLAGS: PriorityFlagDef[] = [
  { type: "Change Order", requiresReason: false },
  { type: "Customer Escalation (Owner Level)", requiresReason: false },
  { type: "Customer Escalation (PM Level)", requiresReason: false },
  { type: "Scope of Work Dispute", requiresReason: true },
  { type: "Labor Issue", requiresReason: true },
  { type: "Property Damage", requiresReason: true },
  { type: "Schedule Conflict", requiresReason: true },
  { type: "Missing Project Details", requiresReason: false },
  { type: "Delay of Payment", requiresReason: true },
  { type: "Wrong Materials", requiresReason: false },
];

export function flagRequiresReason(type: string): boolean {
  return PRIORITY_FLAGS.find((f) => f.type === type)?.requiresReason ?? false;
}

export function priorityLevelColor(level?: string | null): { bg: string; text: string } {
  switch (level) {
    case "High":
      return { bg: "#DC2626", text: "#FFFFFF" };
    case "Medium":
      return { bg: "#D97706", text: "#FFFFFF" };
    case "Low":
      return { bg: "#4B5563", text: "#FFFFFF" };
    default:
      return { bg: "#E5E7EB", text: "#111827" };
  }
}
