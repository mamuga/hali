import { useEffect, useState } from 'react';
import { flushQueuedReports, listQueuedReports } from '../lib/offlineQueue';
import { useOnlineStatus } from './useOnlineStatus';

export function useReportQueue() {
  const online = useOnlineStatus();
  const [queued, setQueued] = useState(listQueuedReports().length);
  useEffect(() => {
    if (!online) return;
    flushQueuedReports().finally(() => setQueued(listQueuedReports().length));
  }, [online]);
  return { queued, online };
}
