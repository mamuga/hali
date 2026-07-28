import { describe, expect, it } from 'vitest';
import { ICPAC_LAYERS, ICPAC_WMS_URL } from '@/lib/icpacLayers';
import { RISK_RAMP, riskColour } from './RiskRanking';
import { PLAYBACK_DAYS, offsetToDate } from './TemporalSlider';

describe('riskColour', () => {
  it('maps the highest score to the top of the ramp', () => {
    expect(riskColour(100, 100)).toBe(RISK_RAMP[RISK_RAMP.length - 1]);
  });

  it('maps a low score to the bottom of the ramp', () => {
    expect(riskColour(1, 1000)).toBe(RISK_RAMP[0]);
  });

  it('never returns undefined for a score above the max', () => {
    // Guards the Math.floor(ratio * len) index, which lands out of bounds at ratio 1.
    expect(RISK_RAMP).toContain(riskColour(500, 100));
  });

  it('falls back to the lowest colour when every score is zero', () => {
    expect(riskColour(0, 0)).toBe(RISK_RAMP[0]);
  });
});

describe('offsetToDate', () => {
  const now = new Date('2026-07-28T12:00:00Z');

  it('maps the maximum offset to today', () => {
    expect(offsetToDate(PLAYBACK_DAYS, now)).toBe('2026-07-28');
  });

  it('maps offset zero to the start of the window', () => {
    expect(offsetToDate(0, now)).toBe('2026-06-28');
  });

  it('moves forward one day per step', () => {
    expect(offsetToDate(29, now)).toBe('2026-07-27');
  });
});

describe('ICPAC layers', () => {
  it('points at the ICPAC GeoServer', () => {
    expect(ICPAC_WMS_URL).toContain('geoportal.icpac.net');
  });

  it('uses only layer names verified against GetCapabilities', () => {
    // The spec's original names (rainfall_anomaly, flood_risk, spi_3month,
    // ea_hazard_zones) are not published by that server and 404.
    const names = ICPAC_LAYERS.map((l) => l.name);
    expect(names).toContain('flood_prone_areas');
    expect(names).toContain('desert_locust_hazard');
    expect(names).not.toContain('rainfall_anomaly');
    expect(names).not.toContain('spi_3month');
  });

  it('keeps every overlay translucent enough to see HALI zones underneath', () => {
    for (const layer of ICPAC_LAYERS) {
      expect(layer.opacity).toBeGreaterThan(0);
      expect(layer.opacity).toBeLessThanOrEqual(0.7);
    }
  });
});
