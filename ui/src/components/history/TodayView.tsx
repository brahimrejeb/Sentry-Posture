import { useEffect, useState } from 'react';

import type { DayHistory, Streaks } from '../../api';
import { api } from '../../api';
import { fmtDuration, fmtPct } from '../../format';
import { DayTimeline } from './DayTimeline';
import { HourBars } from './HourBars';
import { KpiCard } from './KpiCard';

interface Props {
  goalPct: number;
  goalBreaks: number;
}

export function TodayView({ goalPct, goalBreaks }: Props) {
  const [day, setDay] = useState<DayHistory | null>(null);
  const [streaks, setStreaks] = useState<Streaks | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [d, s] = await Promise.all([api.historyToday(), api.streaks()]);
        if (cancelled) return;
        setDay(d);
        setStreaks(s);
        setError(null);
      } catch (err) {
        if (!cancelled) setError(String(err));
      }
    };
    load();
    const id = window.setInterval(load, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  if (error) return <div className="card banner warning">{error}</div>;
  if (!day) return <div className="card">Loading today's data…</div>;

  const t = day.totals;
  const slouchTone = t.slouch_pct <= goalPct ? 'good' : t.slouch_pct < 0.35 ? 'warning' : 'bad';
  const breaksTone = t.breaks >= goalBreaks ? 'good' : t.breaks > 0 ? 'warning' : 'bad';

  return (
    <>
      <div className="card section">
        <h2>Today</h2>
        <div className="kpi-grid">
          <KpiCard
            label="Time at desk"
            value={fmtDuration(t.locked_seconds)}
            hint={t.locked_seconds > 0 ? 'Active monitoring' : 'No data yet'}
          />
          <KpiCard
            label="Time slouching"
            value={
              t.locked_seconds > 0
                ? `${fmtDuration(t.slouch_seconds)} (${fmtPct(t.slouch_pct)})`
                : '—'
            }
            hint={`Goal: ≤ ${fmtPct(goalPct)}`}
            tone={t.locked_seconds > 0 ? slouchTone : 'default'}
          />
          <KpiCard
            label="Breaks"
            value={String(t.breaks)}
            hint={`Goal: ${goalBreaks}`}
            tone={t.locked_seconds > 0 ? breaksTone : 'default'}
          />
          <KpiCard
            label="Longest stretch"
            value={fmtDuration(t.longest_uninterrupted_seconds)}
            hint={`${t.alerts} alert${t.alerts === 1 ? '' : 's'} fired`}
          />
        </div>
      </div>

      <div className="card section">
        <h2>24-hour timeline</h2>
        <DayTimeline buckets={day.buckets} />
        <div className="legend">
          <span className="legend-swatch swatch-upright" /> Upright
          <span className="legend-swatch swatch-slouch" /> Slouching
          <span className="legend-swatch swatch-break" /> Break
        </div>
      </div>

      <div className="card section">
        <h2>By hour</h2>
        <HourBars buckets={day.buckets} />
      </div>

      {streaks && (
        <div className="card section">
          <h2>Streaks</h2>
          <div className="kpi-grid">
            <KpiCard
              label="Good-posture days"
              value={streaks.good_posture_days === 0 ? '—' : `${streaks.good_posture_days} 🔥`}
              hint={`Days in a row with ≤ ${fmtPct(goalPct)} slouching`}
              tone={streaks.good_posture_days >= 3 ? 'good' : 'default'}
            />
            <KpiCard
              label="Break-goal days"
              value={streaks.break_goal_days === 0 ? '—' : `${streaks.break_goal_days} 🔥`}
              hint={`Days in a row with ≥ ${goalBreaks} breaks`}
              tone={streaks.break_goal_days >= 3 ? 'good' : 'default'}
            />
          </div>
        </div>
      )}
    </>
  );
}
