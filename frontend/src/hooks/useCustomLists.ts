import { useEffect, useState, useCallback } from "react";
import { api } from "@/src/api";
import { PRIORITY_FLAGS as DEFAULT_PRIORITY_FLAGS, PriorityFlagDef } from "@/src/priority";

const DEFAULT_BREAK_TYPES = ["Bathroom", "Lunch", "Personal", "Admin Call"];

export type CustomLists = {
  break_types: string[];
  priority_flags: PriorityFlagDef[];
  loaded: boolean;
  reload: () => Promise<void>;
};

/** Load the current user's editable pickable lists (break types + priority flags).
 * Falls back to hard-coded defaults if the API fails or hasn't yet responded.
 */
export function useCustomLists(): CustomLists {
  const [breakTypes, setBreakTypes] = useState<string[]>(DEFAULT_BREAK_TYPES);
  const [flags, setFlags] = useState<PriorityFlagDef[]>(DEFAULT_PRIORITY_FLAGS);
  const [loaded, setLoaded] = useState(false);

  const reload = useCallback(async () => {
    try {
      const res = await api.getUserLists();
      const b = Array.isArray(res.break_types) && res.break_types.length > 0
        ? res.break_types
        : DEFAULT_BREAK_TYPES;
      const f = Array.isArray(res.priority_flags) && res.priority_flags.length > 0
        ? res.priority_flags.map((p: any) => ({
            type: p.type,
            requiresReason: !!p.requires_reason,
          }))
        : DEFAULT_PRIORITY_FLAGS;
      setBreakTypes(b);
      setFlags(f);
    } catch {
      // keep defaults on any error
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { break_types: breakTypes, priority_flags: flags, loaded, reload };
}
