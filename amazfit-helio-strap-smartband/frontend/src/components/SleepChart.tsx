import { useState } from 'react';
import { useHealthData } from '../hooks/useHealthData';
import type { SleepEntry, SleepStage } from '../types';
import InfoTooltip from './InfoTooltip';

const STAGE_COLORS: Record<string, string> = {
  deep: '#6366F1',
  light: '#38BDF8',
  rem: '#A78BFA',
  awake: '#F59E0B',
};

const STAGE_LABELS: Record<string, string> = {
  deep: 'Deep',
  light: 'Light',
  rem: 'REM',
  awake: 'Awake',
};

function fmtHrs(min: number) {
  const h = Math.floor(min / 60);
  const m = min % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function fmtTime(iso: string, tz: string) {
  return new Date(iso).toLocaleTimeString([], { timeZone: tz, hour: '2-digit', minute: '2-digit', hour12: false });
}

function shortDate(dateStr: string) {
  const d = new Date(dateStr + 'T00:00:00');
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return { day: days[d.getDay()], date: `${months[d.getMonth()]} ${d.getDate()}` };
}

export default function SleepChart({ locked, connected }: { locked?: boolean; connected?: boolean }) {
  const { data, loading } = useHealthData<SleepEntry>('/api/sleep?limit=30', 300000);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const tz = localStorage.getItem('tz') || Intl.DateTimeFormat().resolvedOptions().timeZone;

  // Most recent first
  const entries = data;
  const selected = entries.length > 0 ? entries[Math.min(selectedIdx, entries.length - 1)] : null;

  return (
    <div className="bg-gray-900 rounded-xl p-3 h-full flex flex-col">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
          Sleep<InfoTooltip text="Sleep stages: Deep (physical recovery), Light (maintenance), REM (mental recovery), Awake. Select a night to see breakdown." />
        </h2>
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center text-gray-600 text-xs">Loading...</div>
      ) : entries.length === 0 ? (
        locked ? (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-600 text-xs gap-1">
            <span className="text-base">&#128274;</span>
            <span>Requires auth key</span>
          </div>
        ) : !connected ? (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-600 text-xs gap-1">
            <span>Connect to device to sync</span>
          </div>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-600 text-xs gap-1">
            <span>No data yet</span>
            <span className="text-[10px]">Click Sync to fetch from device</span>
          </div>
        )
      ) : (
        <div className="flex-1 min-h-0 flex flex-col gap-1.5 overflow-hidden">
          {/* Night selector strip */}
          <NightSelector entries={entries} selectedIdx={selectedIdx} onSelect={setSelectedIdx} />

          {/* Detail view */}
          {selected && <SleepDetail entry={selected} tz={tz} />}
        </div>
      )}
    </div>
  );
}

/* ── Night selector ── */
function NightSelector({ entries, selectedIdx, onSelect }: {
  entries: SleepEntry[];
  selectedIdx: number;
  onSelect: (idx: number) => void;
}) {
  const canPrev = selectedIdx < entries.length - 1;
  const canNext = selectedIdx > 0;

  return (
    <div className="flex items-center gap-1">
      <button
        onClick={() => canPrev && onSelect(selectedIdx + 1)}
        disabled={!canPrev}
        className={`shrink-0 w-5 h-5 flex items-center justify-center rounded text-[10px] ${canPrev ? 'text-gray-400 hover:text-white hover:bg-gray-800' : 'text-gray-700 cursor-default'}`}
      >
        &#9664;
      </button>
      <div className="flex-1 flex gap-1 overflow-x-auto pb-0.5 scrollbar-hide">
        {entries.map((entry, i) => {
          const { day, date } = shortDate(entry.date);
          const isSelected = i === selectedIdx;
          const actualSleep = entry.deep_minutes + entry.light_minutes + entry.rem_minutes;
          const total = entry.total_minutes || 1;
          return (
            <button
              key={entry.date}
              onClick={() => onSelect(i)}
              className={`shrink-0 flex flex-col items-center px-2 py-1 rounded-lg transition-all ${
                isSelected
                  ? 'bg-gray-800 ring-1 ring-blue-500/50'
                  : 'bg-gray-800/40 hover:bg-gray-800'
              }`}
            >
              <span className={`text-[8px] ${isSelected ? 'text-blue-400' : 'text-gray-500'}`}>{day}</span>
              <span className={`text-[9px] font-medium ${isSelected ? 'text-gray-200' : 'text-gray-400'}`}>{date}</span>
              {/* Mini bar */}
              <div className="w-8 h-1 mt-0.5 rounded-full overflow-hidden flex bg-gray-700">
                <div style={{ width: `${(entry.deep_minutes / total) * 100}%`, backgroundColor: STAGE_COLORS.deep }} />
                <div style={{ width: `${(entry.light_minutes / total) * 100}%`, backgroundColor: STAGE_COLORS.light }} />
                <div style={{ width: `${(entry.rem_minutes / total) * 100}%`, backgroundColor: STAGE_COLORS.rem }} />
                <div style={{ width: `${(entry.awake_minutes / total) * 100}%`, backgroundColor: STAGE_COLORS.awake }} />
              </div>
              <span className={`text-[7px] mt-0.5 ${isSelected ? 'text-gray-400' : 'text-gray-500'}`}>{fmtHrs(actualSleep)}</span>
            </button>
          );
        })}
      </div>
      <button
        onClick={() => canNext && onSelect(selectedIdx - 1)}
        disabled={!canNext}
        className={`shrink-0 w-5 h-5 flex items-center justify-center rounded text-[10px] ${canNext ? 'text-gray-400 hover:text-white hover:bg-gray-800' : 'text-gray-700 cursor-default'}`}
      >
        &#9654;
      </button>
    </div>
  );
}

/* ── Detail view ── */
function SleepDetail({ entry, tz }: { entry: SleepEntry; tz: string }) {
  const { stages } = entry;
  const actualSleep = entry.deep_minutes + entry.light_minutes + entry.rem_minutes;
  const total = entry.total_minutes || 1;

  const stageData = [
    { key: 'deep', label: 'Deep', mins: entry.deep_minutes, desc: 'Physical recovery', icon: '~' },
    { key: 'light', label: 'Light', mins: entry.light_minutes, desc: 'Memory processing', icon: '-' },
    { key: 'rem', label: 'REM', mins: entry.rem_minutes, desc: 'Mental recovery', icon: '*' },
    { key: 'awake', label: 'Awake', mins: entry.awake_minutes, desc: 'Interruptions', icon: '!' },
  ];

  return (
    <div className="flex-1 min-h-0 flex flex-col gap-2 overflow-hidden">
      {/* Total sleep header with donut */}
      <div className="flex items-center gap-3">
        <DonutRing stageData={stageData} total={total} actualSleep={actualSleep} />
        <div className="flex-1">
          <div className="flex items-baseline gap-1.5">
            <span className="text-2xl font-bold text-white leading-none">{fmtHrs(actualSleep)}</span>
            <span className="text-[10px] text-gray-500">asleep</span>
          </div>
          <div className="text-[10px] text-gray-400 mt-0.5">
            {entry.date} &middot; {fmtHrs(total)} in bed
          </div>
          {/* Proportional bar */}
          <div className="w-full h-2 mt-1.5 rounded-full overflow-hidden flex bg-gray-800">
            {stageData.map(({ key, mins }) => (
              <div
                key={key}
                style={{
                  width: `${(mins / total) * 100}%`,
                  backgroundColor: STAGE_COLORS[key],
                }}
                className="transition-all"
              />
            ))}
          </div>
        </div>
      </div>

      {/* Stage breakdown cards */}
      <div className="grid grid-cols-4 gap-1.5">
        {stageData.map(({ key, label, mins, desc }) => {
          const pct = key !== 'awake' && actualSleep > 0
            ? Math.round((mins / actualSleep) * 100)
            : key === 'awake' && total > 0
            ? Math.round((mins / total) * 100)
            : 0;
          return (
            <div
              key={key}
              className="bg-gray-800/60 rounded-lg p-1.5 flex flex-col items-center text-center"
            >
              <div
                className="w-5 h-5 rounded-full flex items-center justify-center mb-0.5"
                style={{ backgroundColor: STAGE_COLORS[key] + '30' }}
              >
                <span className="text-[9px] font-bold" style={{ color: STAGE_COLORS[key] }}>{pct}%</span>
              </div>
              <span className="text-[10px] font-medium" style={{ color: STAGE_COLORS[key] }}>{label}</span>
              <span className="text-xs text-white font-semibold">{fmtHrs(mins)}</span>
              <span className="text-[7px] text-gray-600 leading-tight">{desc}</span>
            </div>
          );
        })}
      </div>

      {/* Hypnogram */}
      {stages && stages.length > 0 && (
        <StageTimeline stages={stages} tz={tz} />
      )}
    </div>
  );
}

/* ── Donut ring with center label ── */
function DonutRing({ stageData, total, actualSleep }: {
  stageData: { key: string; mins: number }[];
  total: number;
  actualSleep: number;
}) {
  const size = 72;
  const stroke = 7;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  const efficiency = total > 0 ? Math.round((actualSleep / total) * 100) : 0;

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#1F2937" strokeWidth={stroke} />
        {stageData.map(({ key, mins }) => {
          const pct = total > 0 ? mins / total : 0;
          const dashLen = pct * circumference;
          const gap = 1;
          const el = (
            <circle
              key={key}
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={STAGE_COLORS[key]}
              strokeWidth={stroke}
              strokeDasharray={`${Math.max(dashLen - gap, 0)} ${circumference - Math.max(dashLen - gap, 0)}`}
              strokeDashoffset={-offset}
              strokeLinecap="round"
            />
          );
          offset += dashLen;
          return el;
        })}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-sm font-bold text-white leading-none">{efficiency}%</span>
        <span className="text-[7px] text-gray-500">quality</span>
      </div>
    </div>
  );
}

/* ── Hypnogram timeline ── */
function StageTimeline({ stages, tz }: { stages: SleepStage[]; tz: string }) {
  const merged: SleepStage[] = [];
  for (const s of stages) {
    const last = merged[merged.length - 1];
    if (last && last.stage === s.stage && last.end === s.start) {
      last.end = s.end;
      last.minutes += s.minutes;
    } else {
      merged.push({ ...s });
    }
  }

  if (merged.length === 0) return null;

  const firstStart = new Date(merged[0].start).getTime();
  const lastEnd = new Date(merged[merged.length - 1].end).getTime();
  const totalSpan = lastEnd - firstStart;
  if (totalSpan <= 0) return null;

  const stageY: Record<string, number> = { awake: 0, rem: 1, light: 2, deep: 3 };
  const stageLabels = ['A', 'R', 'L', 'D'];

  return (
    <div className="flex flex-col">
      <div className="flex justify-between text-[8px] text-gray-600 mb-0.5 px-0.5">
        <span>{fmtTime(merged[0].start, tz)}</span>
        <span className="text-gray-700">Stages</span>
        <span>{fmtTime(merged[merged.length - 1].end, tz)}</span>
      </div>
      <div className="relative h-[52px] bg-gray-800/30 rounded-lg overflow-hidden">
        {/* Y-axis */}
        <div className="absolute left-0 top-0 bottom-0 w-5 flex flex-col justify-between py-1 z-10">
          {stageLabels.map((label) => (
            <span key={label} className="text-[7px] text-gray-600 leading-none text-center">{label}</span>
          ))}
        </div>
        {/* Grid */}
        {[1, 2, 3].map(i => (
          <div key={i} className="absolute left-5 right-0 border-t border-gray-800/60" style={{ top: `${(i / 4) * 100}%` }} />
        ))}
        {/* Blocks */}
        <div className="absolute left-5 right-0 top-0 bottom-0">
          {merged.map((s, i) => {
            const start = new Date(s.start).getTime();
            const end = new Date(s.end).getTime();
            const leftPct = ((start - firstStart) / totalSpan) * 100;
            const widthPct = Math.max(((end - start) / totalSpan) * 100, 0.4);
            const y = stageY[s.stage] ?? 0;
            const topPct = (y / 4) * 100;

            return (
              <div
                key={i}
                className="absolute rounded-[2px] hover:brightness-125 transition-all cursor-default"
                style={{
                  left: `${leftPct}%`,
                  width: `${widthPct}%`,
                  top: `calc(${topPct}% + 1px)`,
                  height: 'calc(25% - 2px)',
                  backgroundColor: STAGE_COLORS[s.stage],
                  opacity: 0.9,
                }}
                title={`${STAGE_LABELS[s.stage]}: ${fmtTime(s.start, tz)} - ${fmtTime(s.end, tz)} (${s.minutes}m)`}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}
