import { useCallback, useEffect, useState } from 'react';

export interface Coords {
  lat: number;
  lng: number;
}

export function useLocation() {
  const [coords, setCoords] = useState<Coords | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const request = useCallback(() => {
    if (!navigator.geolocation) {
      setError('Geolocation not available');
      setLoading(false);
      return;
    }

    setLoading(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setError(null);
        setLoading(false);
      },
      () => {
        setError('Location access denied');
        setLoading(false);
      },
      { timeout: 8000, maximumAge: 60000 },
    );
  }, []);

  useEffect(() => {
    request();
  }, [request]);

  // `request` lets a caller retry after the user denies or dismisses the
  // browser prompt, which the mount-only version could not do.
  return { coords, error, loading, request };
}
