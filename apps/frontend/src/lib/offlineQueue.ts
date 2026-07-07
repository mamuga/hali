import type { CommunityReport } from '@hali/types';

const QUEUE_KEY = 'hali:report_queue';

export interface QueuedReport {
  id: string;
  report: CommunityReport;
  queuedAt: string;
  attempts: number;
}

export const offlineQueue = {
  get(): QueuedReport[] {
    try {
      return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]') as QueuedReport[];
    } catch {
      return [];
    }
  },
  add(report: CommunityReport): void {
    const q = this.get();
    q.push({
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      report,
      queuedAt: new Date().toISOString(),
      attempts: 0,
    });
    localStorage.setItem(QUEUE_KEY, JSON.stringify(q));
  },
  remove(id: string): void {
    localStorage.setItem(
      QUEUE_KEY,
      JSON.stringify(this.get().filter((q) => q.id !== id)),
    );
  },
  incrementAttempts(id: string): void {
    localStorage.setItem(
      QUEUE_KEY,
      JSON.stringify(
        this.get().map((q) => (q.id === id ? { ...q, attempts: q.attempts + 1 } : q)),
      ),
    );
  },
  count(): number {
    return this.get().length;
  },
};
