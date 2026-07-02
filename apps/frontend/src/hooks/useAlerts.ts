import { useEffect, useState } from 'react';
import { fetchAlerts } from '../lib/api';
import type { Alert, Language } from '../lib/types';

export function useAlerts(lang: Language) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        setError(null);
        const data = await fetchAlerts(lang);
        if (active) setAlerts(data);
      } catch {
        if (active) setError('Unable to refresh alerts');
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    const id = window.setInterval(load, 60000);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, [lang]);
  return { alerts, loading, error };
}
