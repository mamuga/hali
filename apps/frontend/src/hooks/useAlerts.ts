import { useCallback, useEffect, useState } from 'react';
import { fetchAlerts } from '../lib/api';
import type { Alert, Language } from '@hali/types';

export function useAlerts(lang: Language = 'sw') {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      setAlerts(await fetchAlerts(lang));
    } catch {
      setError('Could not load alerts.');
    } finally {
      setLoading(false);
    }
  }, [lang]);

  useEffect(() => {
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, [load]);

  return { alerts, loading, error, reload: load };
}
