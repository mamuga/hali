import { useCallback, useState } from 'react';

export function useLocation() {
  const [position, setPosition] = useState<{ lat: number; lng: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const locate = useCallback(() => {
    navigator.geolocation.getCurrentPosition(
      (pos) => setPosition({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => setError('Location unavailable'),
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }, []);
  return { position, error, locate };
}
