import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { RefreshCw, ShieldAlert } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { AlertCard } from '@/components/AlertCard';
import { LanguageSelector } from '@/components/LanguageSelector';
import { OfflineBanner } from '@/components/OfflineBanner';
import { ThemeToggle } from '@/components/ThemeToggle';
import { useAlerts } from '@/hooks/useAlerts';
import { useOnlineStatus } from '@/hooks/useOnlineStatus';
import type { Alert, Language } from '@hali/types';

export function AlertFeed() {
  const [lang, setLang] = useState<Language>('sw');
  const { alerts, loading, error, reload } = useAlerts(lang);
  const online = useOnlineStatus();
  const navigate = useNavigate();

  function handleCardClick(alert: Alert) {
    navigate('/actions', { state: { alertId: alert.id, lang } });
  }

  return (
    <div className="flex h-full flex-col">
      <OfflineBanner show={!online} />

      <header className="sticky top-0 z-40 border-b border-border bg-card/95 px-4 py-3 backdrop-blur-sm">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="rounded-lg bg-primary/10 p-1.5">
              <ShieldAlert className="h-5 w-5 text-primary" strokeWidth={1.5} />
            </div>
            <div>
              <h1 className="text-base font-bold leading-none text-foreground">HALI</h1>
              <p className="mt-0.5 text-[11px] leading-none text-muted-foreground">Early Warning - East Africa</p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <LanguageSelector value={lang} onChange={setLang} />
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={reload} aria-label="Refresh alerts">
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="flex-1 space-y-3 overflow-y-auto px-4 pb-24 pt-4">
        {error && (
          <div className="flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <ShieldAlert className="h-4 w-4 shrink-0" />
            {error}
          </div>
        )}

        {loading && !alerts.length && Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 w-full" />)}

        {!loading && !alerts.length && !error && (
          <div className="px-6 py-20 text-center">
            <div className="mb-4 inline-flex rounded-full bg-green-100 p-4 dark:bg-green-900/30">
              <ShieldAlert className="h-8 w-8 text-green-600 dark:text-green-400" strokeWidth={1.5} />
            </div>
            <p className="mb-1 font-semibold text-foreground">All clear</p>
            <p className="text-sm text-muted-foreground">No active alerts for East Africa. We will notify you if anything changes.</p>
          </div>
        )}

        {alerts.map((alert) => (
          <AlertCard key={alert.id} alert={alert} onClick={() => handleCardClick(alert)} />
        ))}
      </main>
    </div>
  );
}
