import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { offlineQueue } from '../lib/offlineQueue';

const submitReport = vi.fn();
const toastSuccess = vi.fn();

vi.mock('../lib/api', () => ({ submitReport: (r: unknown) => submitReport(r) }));
vi.mock('sonner', () => ({ toast: { success: (m: string) => toastSuccess(m) } }));

// Drives the online/offline branch without touching navigator.
let online = true;
vi.mock('./useOnlineStatus', () => ({ useOnlineStatus: () => online }));

const { useReportQueue } = await import('./useReportQueue');

const report = { lat: 3.1191, lng: 35.5973, hazard_type: 'flood' as const, description: 'Maji yamejaa' };

describe('offline report queue', () => {
  beforeEach(() => {
    localStorage.clear();
    submitReport.mockReset();
    toastSuccess.mockReset();
    online = true;
  });

  afterEach(() => localStorage.clear());

  it('persists a queued report under the documented key', () => {
    offlineQueue.add(report);

    const raw = localStorage.getItem('hali:report_queue');
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw as string);
    expect(parsed).toHaveLength(1);
    expect(parsed[0].report).toEqual(report);
    expect(parsed[0].attempts).toBe(0);
  });

  it('holds reports while offline and does not call the API', () => {
    online = false;
    offlineQueue.add(report);

    const { result } = renderHook(() => useReportQueue());

    expect(result.current.queueCount).toBe(1);
    expect(submitReport).not.toHaveBeenCalled();
    expect(offlineQueue.count()).toBe(1);
  });

  it('flushes the queue and toasts once back online', async () => {
    offlineQueue.add(report);
    offlineQueue.add({ ...report, description: 'Daraja limevunjika' });
    submitReport.mockResolvedValue({ id: 'ok' });

    const { result } = renderHook(() => useReportQueue());

    await waitFor(() => expect(offlineQueue.count()).toBe(0));
    expect(submitReport).toHaveBeenCalledTimes(2);
    expect(toastSuccess).toHaveBeenCalledWith('2 queued reports submitted');
    await waitFor(() => expect(result.current.queueCount).toBe(0));
  });

  it('keeps a failing report queued and counts the attempt', async () => {
    offlineQueue.add(report);
    submitReport.mockRejectedValue(new Error('network'));

    renderHook(() => useReportQueue());

    await waitFor(() => expect(offlineQueue.get()[0]?.attempts).toBe(1));
    expect(offlineQueue.count()).toBe(1);
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('gives up after 3 attempts so a poison report cannot retry forever', async () => {
    offlineQueue.add(report);
    for (let i = 0; i < 3; i++) offlineQueue.incrementAttempts(offlineQueue.get()[0].id);

    renderHook(() => useReportQueue());

    await waitFor(() => expect(submitReport).not.toHaveBeenCalled());
    expect(offlineQueue.count()).toBe(1);
  });

  it('survives corrupt localStorage rather than blanking the app', () => {
    localStorage.setItem('hali:report_queue', 'not json');

    const { result } = renderHook(() => useReportQueue());

    expect(result.current.queueCount).toBe(0);
  });
});
