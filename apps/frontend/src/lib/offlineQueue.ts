import type { CommunityReport } from './types';
import { submitReport } from './api';

const KEY = 'hali:queued-reports';
export type QueuedReport = CommunityReport & { queuedAt: string; id: string };

export function listQueuedReports(): QueuedReport[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) || '[]') as QueuedReport[];
  } catch {
    return [];
  }
}

function save(items: QueuedReport[]) {
  localStorage.setItem(KEY, JSON.stringify(items));
}

export function addQueuedReport(report: CommunityReport): QueuedReport {
  const item = { ...report, id: crypto.randomUUID(), queuedAt: new Date().toISOString() };
  save([...listQueuedReports(), item]);
  return item;
}

export function removeQueuedReport(id: string) {
  save(listQueuedReports().filter((item) => item.id !== id));
}

export async function flushQueuedReports(): Promise<number> {
  let sent = 0;
  for (const item of listQueuedReports()) {
    await submitReport({ lat: item.lat, lng: item.lng, hazard_type: item.hazard_type, description: item.description });
    removeQueuedReport(item.id);
    sent += 1;
  }
  return sent;
}
