import { useEffect, useState } from 'react';

import type { RangeHistory } from '../../api';
import { api } from '../../api';
import { fmtDuration, fmtPct } from '../../format';
import { Heatmap } from './Heatmap';
import { KpiCard } from './KpiCard';

interface Props {
  scope: 'month' | 'year';
  goalPct: number;
}

const TITLE = { month: 'Last 30 days', year: 'Last 12 months' };

export function RangeView({ scope, goalPct }: Props) {
  const [data, setData] = useState<RangeHistory | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fn = scope === 'month' ? api.historyMonth : api.historyYear;
    fn()
      .then((d) => !cancelled && setData(d))
      .catch((err) => !cancelled && setError(String(err)));
    return () => {
      cancelled = true;
    };
  }, [scope]);

  if (error) return <div className="card banner warning">{error}</div>;
  if (!data) return <div className="card">Loading…</div>;

  const active = data.days.filter((d) => d.locked_seconds > 0);
  const totalLocked = active.reduce((s, d) => s + d.locked_seconds, 0);
  const totalSlouch = active.reduce((s, d) => s + d.slouch_seconds, 0);
  const goalMet = active.filter((d) => d.slouch_pct <= goalPct).length;
  const totalBreaks = active.reduce((s, d) => s + d.breaks, 0);

  return (
    <>
      <div className="card section">
        <h2>{TITLE[scope]}</h2>
        <div className="kpi-grid">
          <KpiCard label="Active days" value={String(active.length)} />
          <KpiCard label="Total time at desk" value={fmtDuration(totalLocked)} />
          <KpiCard
            label="Avg slouching"
            value={totalLocked > 0 ? fmtPct(totalSlouch / totalLocked) : '—'}
            hint={`Goal: ≤ ${fmtPct(goalPct)}`}
          />
          <KpiCard
            label="Goal-met days"
            value={
              active.length > 0 ? `${goalMet}/${active.length}` : '0'
            }
            tone={
              active.length > 0 && goalMet / active.length >= 0.7
                ? 'good'
                : 'default'
            }
            hint={`${totalBreaks} breaks total`}
          />
        </div>
      </div>

      <div className="card section">
        <h2>Heatmap</h2>
        <Heatmap days={data.days} cellSize={scope === 'year' ? 12 : 18} showWeekdayAxis={scope === 'year'} />
        <div className="legend heatmap-legend">
          <span>Better</span>
          <span className="heatmap-scale" aria-hidden>
            <span style={{ background: 'var(--posture-great)' }} />
            <span style={{ background: 'var(--posture-good)' }} />
            <span style={{ background: 'var(--posture-okay)' }} />
            <span style={{ background: 'var(--posture-bad)' }} />
            <span style={{ background: 'var(--posture-poor)' }} />
          </span>
          <span>Worse</span>
        </div>
      </div>
    </>
  );
}
