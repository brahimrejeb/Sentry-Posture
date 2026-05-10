import { fmtDuration } from '../format';

interface Props {
  lockedStreakSeconds: number;
  standUpAfterSeconds: number;
  size?: number;
}

export function StandUpRing({
  lockedStreakSeconds,
  standUpAfterSeconds,
  size = 96,
}: Props) {
  const radius = size / 2 - 8;
  const circumference = 2 * Math.PI * radius;
  const progress = standUpAfterSeconds > 0
    ? Math.min(1, lockedStreakSeconds / standUpAfterSeconds)
    : 0;
  const remaining = Math.max(0, standUpAfterSeconds - lockedStreakSeconds);
  const overdue = lockedStreakSeconds >= standUpAfterSeconds;
  const stroke = overdue ? 'var(--warning)' : 'var(--primary)';

  return (
    <div className="standup-ring" title={overdue ? 'Take a break!' : `Break in ${fmtDuration(remaining)}`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--border)"
          strokeWidth={6}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={stroke}
          strokeWidth={6}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - progress)}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: 'stroke-dashoffset 0.4s linear, stroke 0.3s' }}
        />
        <text
          x="50%"
          y="50%"
          textAnchor="middle"
          dominantBaseline="central"
          style={{ fontSize: 14, fontWeight: 600, fill: 'var(--text)' }}
        >
          {overdue ? 'Stand up' : fmtDuration(remaining)}
        </text>
      </svg>
    </div>
  );
}
