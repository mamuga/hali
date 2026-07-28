import { TrendingUp } from 'lucide-react';
import type { CompoundRiskGeoJSON } from '@hali/types';

/**
 * Choropleth colour ramp, light blue (low) to deep red (high).
 *
 * The scale is relative to the highest score currently on the map rather than
 * fixed thresholds: compound risk is an unbounded product of severity, area and
 * report density, so absolute cut-offs would render every country the same
 * colour on a quiet day.
 */
export const RISK_RAMP = ['#bae6fd', '#7dd3fc', '#fbbf24', '#f97316', '#dc2626'];

export function riskColour(score: number, max: number): string {
  if (max <= 0) return RISK_RAMP[0];
  const ratio = Math.min(score / max, 1);
  const index = Math.min(Math.floor(ratio * RISK_RAMP.length), RISK_RAMP.length - 1);
  return RISK_RAMP[index];
}

interface Props {
  data: CompoundRiskGeoJSON | null;
  onSelect?: (iso2: string) => void;
}

export function RiskRanking({ data, onSelect }: Props) {
  const features = data?.features ?? [];
  if (features.length === 0) return null;

  const max = Math.max(...features.map((f) => f.properties.compound_risk_score));
  const top = [...features]
    .sort((a, b) => b.properties.compound_risk_score - a.properties.compound_risk_score)
    .slice(0, 5);

  return (
    <div className="rounded-lg border border-border bg-card/95 p-3 shadow-md backdrop-blur-sm">
      <h3 className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        <TrendingUp className="h-3 w-3" />
        Most at risk now
      </h3>
      <ol className="space-y-1.5">
        {top.map((f, i) => {
          const p = f.properties;
          return (
            <li key={p.iso2}>
              <button
                onClick={() => onSelect?.(p.iso2)}
                className="flex w-full items-center gap-2 rounded px-1 py-0.5 text-left transition-colors hover:bg-muted"
              >
                <span className="w-3 text-[10px] text-muted-foreground">{i + 1}</span>
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-sm"
                  style={{ background: riskColour(p.compound_risk_score, max) }}
                />
                <span className="flex-1 truncate text-xs font-medium">{p.country}</span>
                <span className="text-[10px] text-muted-foreground">
                  {p.dominant_hazard} · {p.community_reports_14d} rep
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
