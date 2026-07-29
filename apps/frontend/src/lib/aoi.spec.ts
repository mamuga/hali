import { describe, it, expect, vi } from 'vitest';

// The real module pulls in geoman and its stylesheet; stub both so the config
// can be asserted without loading 274 KB of plugin into the test environment.
vi.mock('@geoman-io/leaflet-geoman-free', () => ({}));
vi.mock('@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css', () => ({}));

const { DRAW_CONTROLS, AOI_STYLE, enableDrawControls } = await import('./aoi');

describe('draw controls', () => {
  it('offers only shapes that enclose an area', () => {
    // The backend rejects anything that is not a Polygon or MultiPolygon, so
    // offering a line or marker tool would let the user draw something that
    // can only ever come back as an error.
    expect(DRAW_CONTROLS.drawPolygon).toBe(true);
    expect(DRAW_CONTROLS.drawRectangle).toBe(true);
    expect(DRAW_CONTROLS.drawPolyline).toBe(false);
    expect(DRAW_CONTROLS.drawMarker).toBe(false);
    expect(DRAW_CONTROLS.drawCircle).toBe(false);
    expect(DRAW_CONTROLS.drawCircleMarker).toBe(false);
    expect(DRAW_CONTROLS.drawText).toBe(false);
  });

  it('allows the drawn shape to be adjusted and removed', () => {
    expect(DRAW_CONTROLS.editMode).toBe(true);
    expect(DRAW_CONTROLS.dragMode).toBe(true);
    expect(DRAW_CONTROLS.removalMode).toBe(true);
  });

  it('keeps the toolbar clear of the layer switcher', () => {
    expect(DRAW_CONTROLS.position).toBe('topleft');
  });

  it('styles the area distinctly from alert zones', () => {
    // Dashed, so a drawn selection never reads as an official alert boundary.
    expect(AOI_STYLE.dashArray).toBeTruthy();
    expect(AOI_STYLE.fillOpacity).toBeLessThan(0.2);
  });
});

describe('attaching geoman to an existing map', () => {
  function fakeMap(withPm: boolean) {
    const pm = { addControls: vi.fn(), setGlobalOptions: vi.fn() };
    return { map: withPm ? { pm } : ({} as Record<string, unknown>), pm };
  }

  it('uses the existing pm instance when the map already has one', async () => {
    const { map, pm } = fakeMap(true);

    enableDrawControls(map as never);

    expect(pm.addControls).toHaveBeenCalledWith(DRAW_CONTROLS);
    expect(pm.setGlobalOptions).toHaveBeenCalled();
  });

  it('throws a clear error when geoman failed to expose L.PM', async () => {
    // Geoman registers through L.Map.addInitHook, which only fires for maps
    // built after it loads. This module is imported lazily, so the map already
    // exists and pm must be attached by hand — if L.PM is missing entirely,
    // fail loudly rather than throwing "cannot read addControls of undefined".
    const { map } = fakeMap(false);

    expect(() => enableDrawControls(map as never)).toThrow(/L\.PM\.Map is unavailable/);
  });
});
