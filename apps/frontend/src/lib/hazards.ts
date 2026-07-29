import {
  AlertTriangle,
  Biohazard,
  Bug,
  Flame,
  HeartPulse,
  Mountain,
  Sun,
  Thermometer,
  Waves,
  Wind,
  type LucideIcon,
} from 'lucide-react';
import type { HazardType } from '@hali/types';

/**
 * Single source of truth for hazard presentation.
 *
 * The icon map and the report-form chip list were previously separate literals
 * that had already drifted (the form offered no cyclone icon path), so adding a
 * hazard meant editing two places and silently falling through to the generic
 * warning triangle if you missed one.
 */
export interface HazardMeta {
  value: HazardType;
  /** Shown on the report form chips. */
  label: string;
  icon: LucideIcon;
}

export const HAZARDS: readonly HazardMeta[] = [
  { value: 'flood', label: 'Flood', icon: Waves },
  { value: 'drought', label: 'Drought', icon: Sun },
  { value: 'locust', label: 'Locust swarm', icon: Bug },
  { value: 'cyclone', label: 'Cyclone', icon: Wind },
  { value: 'heatwave', label: 'Heatwave', icon: Thermometer },
  { value: 'landslide', label: 'Landslide', icon: Mountain },
  { value: 'wildfire', label: 'Wildfire', icon: Flame },
  { value: 'epidemic', label: 'Disease outbreak', icon: Biohazard },
  { value: 'health', label: 'Health emergency', icon: HeartPulse },
  { value: 'other', label: 'Other', icon: AlertTriangle },
] as const;

const BY_VALUE = new Map(HAZARDS.map((h) => [h.value, h]));

export function hazardIcon(hazard: string | null | undefined): LucideIcon {
  return BY_VALUE.get(hazard as HazardType)?.icon ?? AlertTriangle;
}

export function hazardLabel(hazard: string | null | undefined): string {
  return BY_VALUE.get(hazard as HazardType)?.label ?? 'Other';
}
