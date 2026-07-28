import { Loader2, MapPin, Radar, Users, X } from 'lucide-react';
import type { SpatialAnalysis } from '@hali/types';

const SEV_COLOUR: Record<string, string> = {
  red: '#dc2626',
  orange: '#ea580c',
  green: '#16a34a',
};

interface Props {
  analysis: SpatialAnalysis | null;
  loading: boolean;
  error: boolean;
  onClose: () => void;
}

function formatPopulation(value: number | null): string | null {
  // null means WorldPop has not answered, which is not the same as zero people.
  if (value == null) return null;
  return value.toLocaleString();
}

export function AnalysisPanel({ analysis, loading, error, onClose }: Props) {
  return (
    <aside
      className="absolute right-0 top-0 z-[1100] flex h-full w-full max-w-sm flex-col border-l border-border bg-card/97 shadow-xl backdrop-blur-sm"
      aria-label="Location analysis"
    >
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <Radar className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold">Analysis for this location</h2>
        </div>
        <button
          onClick={onClose}
          className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          aria-label="Close analysis panel"
        >
          <X className="h-4 w-4" />
        </button>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-3 text-sm">
        {loading && (
          <div className="flex items-center gap-2 py-8 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Analysing…
          </div>
        )}

        {!loading && error && (
          <p className="py-8 text-muted-foreground">Could not analyse this location. Try again.</p>
        )}

        {!loading && !error && analysis && (
          <div className="space-y-4">
            <div className="flex items-start gap-2 text-muted-foreground">
              <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span className="text-xs">
                {analysis.country ?? 'Outside IGAD member states'}
                <br />
                {analysis.location.lat.toFixed(3)}, {analysis.location.lng.toFixed(3)}
              </span>
            </div>

            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Nearest alerts
              </h3>
              {analysis.nearest_alerts.length === 0 ? (
                <p className="text-xs text-muted-foreground">No active alerts within 500 km.</p>
              ) : (
                <ul className="space-y-2">
                  {analysis.nearest_alerts.map((a) => {
                    const colour = SEV_COLOUR[a.severity] ?? '#16a34a';
                    const population = formatPopulation(a.population_exposed);
                    return (
                      <li key={a.id} className="rounded-lg border border-border p-2.5">
                        <div className="flex items-center gap-2">
                          <span
                            className="rounded px-1.5 py-0.5 text-[10px] font-semibold"
                            style={{ background: `${colour}22`, color: colour }}
                          >
                            {a.severity.toUpperCase()}
                          </span>
                          <span className="text-xs font-medium uppercase">{a.hazard_type}</span>
                          <span className="ml-auto text-xs text-muted-foreground">{a.dist_km} km</span>
                        </div>
                        <p className="mt-1.5 text-xs leading-snug">{a.headline}</p>
                        {population && (
                          <p className="mt-1.5 flex items-center gap-1 text-[11px] text-muted-foreground">
                            <Users className="h-3 w-3" />~{population} people in zone
                          </p>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>

            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Community reports (7 days)
              </h3>
              <p className="text-2xl font-semibold leading-none">{analysis.nearby_reports_7d}</p>
              {analysis.report_breakdown.length > 0 && (
                <ul className="mt-2 space-y-0.5">
                  {analysis.report_breakdown.map((b) => (
                    <li key={b.label} className="text-xs text-muted-foreground">
                      • {b.count}× {b.label.replace(/_/g, ' ')}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Emerging hotspot
              </h3>
              {analysis.emerging_hotspots_nearby > 0 ? (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-2.5">
                  <p className="text-xs font-semibold text-amber-600 dark:text-amber-400">DETECTED</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {analysis.emerging_hotspots_nearby} cluster
                    {analysis.emerging_hotspots_nearby !== 1 ? 's' : ''} within 100 km with no official alert
                    issued.
                  </p>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">None detected within 100 km.</p>
              )}
            </section>
          </div>
        )}
      </div>
    </aside>
  );
}
