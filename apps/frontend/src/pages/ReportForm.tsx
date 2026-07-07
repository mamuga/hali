import { useState } from 'react';
import { Loader2, MapPin, Radio } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { useLocation } from '@/hooks/useLocation';
import { useOnlineStatus } from '@/hooks/useOnlineStatus';
import { submitReport } from '@/lib/api';
import { offlineQueue } from '@/lib/offlineQueue';
import { cn } from '@/lib/utils';
import type { CommunityReport, HazardType } from '@hali/types';

const HAZARDS: { value: HazardType; label: string }[] = [
  { value: 'flood', label: 'Flood' },
  { value: 'drought', label: 'Drought' },
  { value: 'locust', label: 'Locust swarm' },
  { value: 'health', label: 'Health emergency' },
  { value: 'cyclone', label: 'Cyclone' },
  { value: 'other', label: 'Other' },
];

export function ReportForm() {
  const { coords, error: locError, loading: locLoading } = useLocation();
  const online = useOnlineStatus();
  const [hazard, setHazard] = useState<HazardType>('flood');
  const [description, setDesc] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit() {
    if (description.trim().length < 5) {
      toast.error('Please describe what you observed (at least 5 characters)');
      return;
    }

    const report: CommunityReport = {
      lat: coords?.lat ?? 0,
      lng: coords?.lng ?? 0,
      hazard_type: hazard,
      description: description.trim(),
    };

    setSubmitting(true);

    if (!online) {
      offlineQueue.add(report);
      toast.info('Saved offline - will submit when you reconnect');
      setDesc('');
      setSubmitting(false);
      return;
    }

    try {
      await toast.promise(submitReport(report), {
        loading: 'Submitting report...',
        success: 'Report received. Thank you.',
        error: () => {
          offlineQueue.add(report);
          return 'Network error - report saved for later';
        },
      });
      setDesc('');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="h-full overflow-y-auto pb-24">
      <div className="mx-auto max-w-xl space-y-4 px-4 pt-5">
        <div className="flex items-center gap-2">
          <Radio className="h-5 w-5 text-primary" strokeWidth={1.5} />
          <h2 className="text-lg font-bold">Report a Hazard</h2>
        </div>
        <p className="-mt-2 text-sm text-muted-foreground">Share what you observe to help your community.</p>

        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <MapPin className="h-3.5 w-3.5 shrink-0" />
          {locLoading && 'Detecting location...'}
          {!locLoading && coords && `${coords.lat.toFixed(4)}, ${coords.lng.toFixed(4)}`}
          {!locLoading && locError && locError}
        </div>

        <div className="space-y-2">
          <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Hazard type</label>
          <div className="flex flex-wrap gap-2">
            {HAZARDS.map((h) => (
              <button
                key={h.value}
                onClick={() => setHazard(h.value)}
                className={cn(
                  'rounded-lg border px-3.5 py-2 text-sm font-medium transition-all duration-150',
                  hazard === h.value
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border bg-card text-muted-foreground hover:border-primary/50 hover:text-foreground',
                )}
              >
                {h.label}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <label htmlFor="description" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            What did you observe?
          </label>
          <Textarea
            id="description"
            rows={4}
            value={description}
            onChange={(e) => setDesc(e.target.value)}
            placeholder="Describe what you see - flooding roads, locust swarms, dry rivers..."
            maxLength={500}
            className="resize-none text-sm"
          />
          <p className="text-right text-xs text-muted-foreground">{description.length}/500</p>
        </div>

        {!online && (
          <Card className="border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/40">
            <CardContent className="px-4 py-3">
              <p className="text-xs text-amber-800 dark:text-amber-300">
                You are offline. Your report will be queued and submitted automatically when you reconnect.
              </p>
            </CardContent>
          </Card>
        )}

        <Button className="h-11 w-full text-base font-semibold" onClick={handleSubmit} disabled={submitting || description.trim().length < 5}>
          {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {online ? 'Submit Report' : 'Save Report Offline'}
        </Button>
      </div>
    </div>
  );
}
