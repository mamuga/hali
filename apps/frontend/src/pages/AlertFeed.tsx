import { useState } from 'react';
import { AlertCard } from '../components/AlertCard';
import { LanguageSelector } from '../components/LanguageSelector';
import { OfflineBanner } from '../components/OfflineBanner';
import { useAlerts } from '../hooks/useAlerts';
import type { Language } from '../lib/types';

export function AlertFeed() {
  const [lang, setLang] = useState<Language>('en');
  const { alerts, loading, error } = useAlerts(lang);
  return <main className="page"><OfflineBanner /><header className="page-header"><div><h1>HALI Alerts</h1><p>Local warnings and action guidance for East Africa.</p></div><LanguageSelector value={lang} onChange={setLang} /></header>{loading && <div className="skeleton">Loading alerts...</div>}{error && <div className="notice">{error}</div>}{!loading && alerts.length === 0 && <div className="empty">No active alerts for the selected language.</div>}<section className="feed">{alerts.map((alert) => <AlertCard key={alert.id} alert={alert} />)}</section></main>;
}
