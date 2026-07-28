import { Clock, Play, Square } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

export const PLAYBACK_DAYS = 30;

/** Day offset -> ISO date string, where 0 is PLAYBACK_DAYS ago and 30 is today. */
export function offsetToDate(offset: number, now = new Date()): string {
  const d = new Date(now);
  d.setUTCDate(d.getUTCDate() - (PLAYBACK_DAYS - offset));
  return d.toISOString().slice(0, 10);
}

interface Props {
  /** null disables playback and shows only currently-active alerts. */
  value: number | null;
  onChange: (offset: number | null) => void;
}

export function TemporalSlider({ value, onChange }: Props) {
  const [playing, setPlaying] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!playing) return;
    timerRef.current = setInterval(() => {
      onChange(value == null || value >= PLAYBACK_DAYS ? 0 : value + 1);
    }, 700);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [playing, value, onChange]);

  // Stop the timer when playback is switched off entirely.
  useEffect(() => {
    if (value == null) setPlaying(false);
  }, [value]);

  const active = value != null;

  return (
    <div className="rounded-lg border border-border bg-card/95 p-2.5 shadow-md backdrop-blur-sm">
      <div className="flex items-center gap-2">
        <button
          onClick={() => onChange(active ? null : PLAYBACK_DAYS)}
          className={`flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-medium transition-colors ${
            active ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'
          }`}
          aria-pressed={active}
        >
          <Clock className="h-3 w-3" />
          30-day playback
        </button>

        {active && (
          <button
            onClick={() => setPlaying((p) => !p)}
            className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            aria-label={playing ? 'Pause playback' : 'Play playback'}
          >
            {playing ? <Square className="h-3 w-3" /> : <Play className="h-3 w-3" />}
          </button>
        )}
      </div>

      {active && (
        <div className="mt-2 w-56">
          <input
            type="range"
            min={0}
            max={PLAYBACK_DAYS}
            value={value}
            onChange={(e) => {
              setPlaying(false);
              onChange(Number(e.target.value));
            }}
            className="h-1 w-full cursor-pointer appearance-none rounded-full bg-muted accent-primary"
            aria-label="Playback day"
          />
          <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
            <span>{offsetToDate(0)}</span>
            <span className="font-semibold text-foreground">{offsetToDate(value)}</span>
            <span>today</span>
          </div>
        </div>
      )}
    </div>
  );
}
