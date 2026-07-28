import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { offlineQueue } from '../lib/offlineQueue';
import { submitReport } from '../lib/api';
import { useOnlineStatus } from './useOnlineStatus';

export function useReportQueue() {
  const online = useOnlineStatus();
  // Must be wrapped: React treats a bare function as a lazy initialiser and
  // calls it unbound, so `offlineQueue.count` would run with `this` undefined
  // and throw inside `this.get()`.
  const [count, setCount] = useState(() => offlineQueue.count());

  const refresh = useCallback(() => setCount(offlineQueue.count()), []);

  useEffect(() => {
    if (!online) return;
    const pending = offlineQueue.get().filter((q) => q.attempts < 3);
    if (!pending.length) return;

    (async () => {
      let synced = 0;
      for (const item of pending) {
        try {
          await submitReport(item.report);
          offlineQueue.remove(item.id);
          synced++;
        } catch {
          offlineQueue.incrementAttempts(item.id);
        }
      }
      if (synced > 0) {
        toast.success(`${synced} queued report${synced > 1 ? 's' : ''} submitted`);
        refresh();
      }
    })();
  }, [online, refresh]);

  return { queueCount: count, refresh };
}
