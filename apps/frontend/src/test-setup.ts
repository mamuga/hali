// jsdom does not implement matchMedia, which ThemeProvider calls on mount to
// resolve the system colour scheme. Without this stub every test that renders
// the app tree throws "window.matchMedia is not a function".
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}
