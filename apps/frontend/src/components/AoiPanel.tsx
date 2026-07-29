import { AlertTriangle, Loader2, Radar, Trash2, Users, X } from 'lucide-react';
import { hazardIcon, hazardLabel } from '@/lib/hazards';
import type { PolygonQueryResult } from '@hali/types';

const SEV_COLOUR: Record<string, string> = {
  red: '#dc2626',
  orange: '#ea580c',
  green: '#16a34a',
};

interface Props {
  result: PolygonQueryResult | null;
  loading: boolean;
  error: string | null;
  onClear: () => void;
  onClose: () => void;
}

function formatArea(km2: number): string {
  if (km2 >= 1000) return `${Math.round(km2).toLocaleString()} km²`;
  return `${km2.toLocaleString()} km²`;
}

function formatPeople(value: number): string {
  if (value >= 1_000_000) return `~${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `~${Math.round(value / 1000)}k`;
  return `~${value}`;
}

export function AoiPanel({ result, loading, error, onClear, onClose }: Props) {
  const empty =
    result &&
    result.alerts.length === 0 &&
    result.report_count === 0 &&
    result.emerging_hotspots === 0;

  return (
    <aside
      className="absolute right-0 top-0 z-[1100] flex h-full w-full max-w-sm flex-col border-l border-border bg-card/97 shadow-xl backdrop-blur-sm"
      aria-label="Area of interest analysis"
    >
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <Radar className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold">Area of interest</h2>
        </div>
        <button
          onClick={onClose}
          className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          aria-label="Close area analysis"
        >
          <X className="h-4 w-4" />
        </button>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-3 text-sm">
        {loading && (
          <div className="flex items-center gap-2 py-8 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Analysing the area you drew…
          </div>
        )}

        {!loading && error && (
          <div className="flex items-start gap-2 rounded-lg border border-destructive/20 bg-destructive/10 px-3 py-2.5 text-destructive">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span className="text-xs leading-relaxed">{error}</span>
          </div>
        )}

        {!loading && !error && result && (
          <>
            <div className="mb-4 flex items-baseline gap-2">
              <span className="text-2xl font-semibold">{formatArea(result.area_km2)}</span>
              <span className="text-xs text-muted-foreground">selected</span>
            </div>

            {empty && (
              <p className="rounded-lg border border-border bg-muted/40 px-3 py-6 text-center text-xs text-muted-foreground">
                No active alerts, community reports, or emerging hotspots in this area.
              </p>
            )}

            {result.alerts.length > 0 && (
              <section className="mb-4">
                <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Active alerts ({result.alert_count})
                  {/* The list is capped server-side; say so rather than let the
                      heading imply the area holds only what is shown. */}
                  {result.alert_count > result.alerts.length && (
                    <span className="ml-1 font-normal normal-case tracking-normal">
                      — showing the {result.alerts.length} most severe
                    </span>
                  )}
                </h3>
                <ul className="space-y-2">
                  {result.alerts.map((a) => {
                    const Icon = hazardIcon(a.hazard_type);
                    const colour = SEV_COLOUR[a.severity] ?? '#16a34a';
                    return (
                      <li
                        key={a.id}
                        className="rounded-lg border border-border bg-background/60 px-3 py-2.5"
                      >
                        <div className="flex items-start gap-2">
                          <Icon className="mt-0.5 h-4 w-4 shrink-0" style={{ color: colour }} />
                          <div className="min-w-0 flex-1">
                            <p className="text-xs font-medium leading-snug">{a.headline}</p>
                            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                              <span
                                className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
                                style={{ background: `${colour}22`, color: colour }}
                              >
                                {a.severity.toUpperCase()}
                              </span>
                              <span className="text-[10px] text-muted-foreground">
                                {a.overlap_km2.toLocaleString()} km² inside selection
                              </span>
                            </div>
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </section>
            )}

            {result.report_count > 0 && (
              <section className="mb-4">
                <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Community reports (14 days)
                </h3>
                <p className="text-2xl font-semibold">{result.report_count}</p>
                {result.report_hazards.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {result.report_hazards.map((h) => (
                      <span
                        key={h}
                        className="rounded-full border border-border px-2 py-0.5 text-[10px] text-muted-foreground"
                      >
                        {hazardLabel(h)}
                      </span>
                    ))}
                  </div>
                )}
              </section>
            )}

            {result.emerging_hotspots > 0 && (
              <section className="mb-4">
                <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Emerging hotspots
                </h3>
                <p className="text-xs">
                  <span className="text-lg font-semibold">{result.emerging_hotspots}</span>{' '}
                  <span className="text-muted-foreground">
                    community cluster{result.emerging_hotspots === 1 ? '' : 's'} with no official
                    alert
                  </span>
                </p>
              </section>
            )}

            {/* Rendered only when a population grid is loaded. null means we have
                not measured this area, which is not the same as nobody living here. */}
            {result.population_estimate != null && (
              <section className="mb-4 flex items-center gap-2 rounded-lg border border-border bg-background/60 px-3 py-2.5">
                <Users className="h-4 w-4 shrink-0 text-primary" />
                <span className="text-xs">
                  <strong>{formatPeople(result.population_estimate)}</strong> people in this area
                </span>
              </section>
            )}
          </>
        )}
      </div>

      <footer className="border-t border-border px-4 py-3">
        <button
          onClick={onClear}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-border px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <Trash2 className="h-3.5 w-3.5" />
          Clear selection
        </button>
      </footer>
    </aside>
  );
}
