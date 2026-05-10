import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from './App';
import type { Status } from './api';

const idleStatus: Status = {
  monitoring: false,
  state: 'idle',
  calibrated: false,
  is_slouching: false,
  person_detected: false,
  people_in_frame: 0,
  settling: false,
  welcome_back: false,
  current_cva: null,
  baseline_cva: null,
  deviation: null,
  last_alert_at: null,
  sensitivity_threshold: 12,
  slouch_time_threshold: 10,
  alert_cooldown: 30,
  current_model: 'full',
  available_models: ['full'],
  locked_streak_seconds: 0,
  stand_up_after_seconds: 3000,
  daily_slouch_goal_pct: 0.2,
  daily_break_goal: 5,
  mode: 'simple',
};

describe('<App/>', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.endsWith('/api/devices')) {
          return new Response(JSON.stringify({ devices: [{ id: '0', name: 'Camera 0' }] }), {
            headers: { 'Content-Type': 'application/json' },
          });
        }
        if (url.endsWith('/api/status')) {
          return new Response(JSON.stringify(idleStatus), {
            headers: { 'Content-Type': 'application/json' },
          });
        }
        return new Response('{}', { headers: { 'Content-Type': 'application/json' } });
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the brand and the idle status', async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText('Sentry')).toBeInTheDocument());
    expect(screen.getByText(/Monitoring is stopped/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /start monitoring/i })).toBeInTheDocument();
  });
});
