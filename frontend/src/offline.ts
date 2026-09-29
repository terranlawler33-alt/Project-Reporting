import { storage } from "@/src/utils/storage";
import { apiRequest } from "@/src/api";

export type QueuedKind = "visit" | "break-start" | "break-end" | "sms";
export type QueuedAction = {
  id: string;
  kind: QueuedKind;
  path: string;
  method: "POST";
  body: any;
  ts: number;
};

const KEY = "paintops.offline.queue";

async function readQueue(): Promise<QueuedAction[]> {
  const raw = await storage.getItem<string>(KEY, "");
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

async function writeQueue(items: QueuedAction[]) {
  await storage.setItem(KEY, JSON.stringify(items));
}

export async function enqueueAction(kind: QueuedKind, path: string, body: any) {
  const items = await readQueue();
  const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  items.push({ id, kind, path, method: "POST", body, ts: Date.now() });
  await writeQueue(items);
  return id;
}

export async function pendingCount(): Promise<number> {
  return (await readQueue()).length;
}

export async function flushQueue(): Promise<{ sent: number; failed: number }> {
  let sent = 0;
  let failed = 0;
  const items = await readQueue();
  const remaining: QueuedAction[] = [];
  for (const item of items) {
    try {
      await apiRequest(item.path, {
        method: item.method,
        body: JSON.stringify(item.body),
      });
      sent += 1;
    } catch {
      failed += 1;
      remaining.push(item);
    }
  }
  await writeQueue(remaining);
  return { sent, failed };
}

export async function clearQueue() {
  await writeQueue([]);
}
