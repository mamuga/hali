import { useEffect, useState } from 'react';
import { useLocation as useRouterLocation } from 'react-router-dom';
import { BookOpen, Copy } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { LanguageSelector } from '@/components/LanguageSelector';
import { SeverityBadge } from '@/components/SeverityBadge';
import { fetchActionCard, fetchAlerts } from '@/lib/api';
import type { Alert, Language, Livelihood } from '@hali/types';

const LIVELIHOODS: { value: Livelihood; label: string }[] = [
  { value: 'farmer', label: 'Farmer' },
  { value: 'pastoralist', label: 'Pastoralist' },
  { value: 'fisherfolk', label: 'Fisherfolk' },
  { value: 'urban', label: 'Urban resident' },
];

export function ActionCardPage() {
  const routerState = useRouterLocation().state as { alertId?: string; lang?: Language } | null;
  const [lang, setLang] = useState<Language>(routerState?.lang ?? 'en');
  const [livelihood, setLive] = useState<Livelihood>('farmer');
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [selectedId, setSelId] = useState<string>(routerState?.alertId ?? '');
  const [steps, setSteps] = useState('');
  const [loading, setLoading] = useState(false);
  const [fetchingAlerts, setFetchingAlerts] = useState(true);

  useEffect(() => {
    setFetchingAlerts(true);
    fetchAlerts(lang, undefined, undefined, 10)
      .then((data) => {
        setAlerts(data);
        setSelId((current) => current || data[0]?.id || '');
      })
      .catch(() => toast.error('Failed to load alerts'))
      .finally(() => setFetchingAlerts(false));
  }, [lang]);

  useEffect(() => {
    if (!selectedId) return;
    setLoading(true);
    setSteps('');
    fetchActionCard(selectedId, livelihood, lang)
      .then((card) => {
        if (card) setSteps(card.steps);
        else toast.info('No action card available. Try a different livelihood or language.');
      })
      .catch(() => toast.error('Failed to load action card'))
      .finally(() => setLoading(false));
  }, [selectedId, livelihood, lang]);

  const selected = alerts.find((a) => a.id === selectedId);

  function copySteps() {
    navigator.clipboard.writeText(steps);
    toast.success('Copied to clipboard');
  }

  return (
    <div className="h-full overflow-y-auto pb-24">
      <div className="mx-auto max-w-xl space-y-4 px-4 pt-5">
        <div className="flex items-center gap-2">
          <BookOpen className="h-5 w-5 text-primary" strokeWidth={1.5} />
          <h2 className="text-lg font-bold">Action Plan</h2>
        </div>

        <Card>
          <CardContent className="space-y-3 pt-4">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Alert</label>
              {fetchingAlerts ? (
                <Skeleton className="h-9 w-full" />
              ) : alerts.length ? (
                <Select value={selectedId} onValueChange={setSelId}>
                  <SelectTrigger className="text-sm">
                    <SelectValue placeholder="Select alert" />
                  </SelectTrigger>
                  <SelectContent>
                    {alerts.map((a) => (
                      <SelectItem key={a.id} value={a.id} className="text-sm">
                        {a.headline ?? `${a.hazard_type} - ${(a.affected_countries ?? []).join(', ')}`}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <div className="rounded-md border border-border bg-muted px-3 py-2 text-sm text-muted-foreground">No active alerts</div>
              )}
              {selected && (
                <div className="flex items-center gap-2 pt-0.5">
                  <SeverityBadge severity={selected.severity} />
                  <span className="text-xs text-muted-foreground">{(selected.affected_countries ?? []).join(', ')}</span>
                </div>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Livelihood</label>
                <Select value={livelihood} onValueChange={(v) => setLive(v as Livelihood)}>
                  <SelectTrigger className="text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {LIVELIHOODS.map((l) => (
                      <SelectItem key={l.value} value={l.value} className="text-sm">
                        {l.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Language</label>
                <LanguageSelector value={lang} onChange={setLang} className="w-full" />
              </div>
            </div>
          </CardContent>
        </Card>

        {loading && <Skeleton className="h-48 w-full" />}

        {!loading && steps && (
          <Card className="border-primary/30">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-semibold uppercase tracking-wider text-primary">Next 48 hours</CardTitle>
                <Button variant="ghost" size="icon" className="h-7 w-7" onClick={copySteps} aria-label="Copy action steps">
                  <Copy className="h-3.5 w-3.5" />
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-foreground">{steps}</pre>
            </CardContent>
          </Card>
        )}

        {!loading && !steps && selectedId && <div className="py-10 text-center text-sm text-muted-foreground">No action card found for this selection.</div>}
      </div>
    </div>
  );
}
