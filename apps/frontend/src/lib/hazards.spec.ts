import { describe, it, expect } from 'vitest';
import { HAZARDS, hazardIcon, hazardLabel } from './hazards';
import type { HazardType } from '@hali/types';

// Kept in step with the backend's HazardType enum and the DB CHECK constraint
// (see apps/backend/tests/test_domain_vocabularies.py).
const EXPECTED: HazardType[] = [
  'flood',
  'drought',
  'locust',
  'cyclone',
  'heatwave',
  'landslide',
  'wildfire',
  'epidemic',
  'health',
  'other',
];

describe('hazard metadata', () => {
  it('covers every hazard the backend can emit', () => {
    expect(HAZARDS.map((h) => h.value).sort()).toEqual([...EXPECTED].sort());
  });

  it('gives each hazard a distinct icon so chips are scannable', () => {
    const icons = new Set(HAZARDS.map((h) => h.icon));
    expect(icons.size).toBe(HAZARDS.length);
  });

  it('gives each hazard a distinct label', () => {
    const labels = new Set(HAZARDS.map((h) => h.label));
    expect(labels.size).toBe(HAZARDS.length);
  });

  it('resolves an icon for every known hazard', () => {
    for (const hazard of EXPECTED) {
      expect(hazardIcon(hazard)).toBeDefined();
    }
  });

  it('falls back to the warning icon for an unknown or missing hazard', () => {
    const fallback = hazardIcon('other');
    expect(hazardIcon('meteor-strike')).toBe(fallback);
    expect(hazardIcon(null)).toBe(fallback);
    expect(hazardIcon(undefined)).toBe(fallback);
  });

  it('labels an unknown hazard rather than rendering blank', () => {
    expect(hazardLabel('meteor-strike')).toBe('Other');
    expect(hazardLabel(null)).toBe('Other');
  });

  it('distinguishes epidemic from general health', () => {
    expect(hazardIcon('epidemic')).not.toBe(hazardIcon('health'));
    expect(hazardLabel('epidemic')).not.toBe(hazardLabel('health'));
  });
});
