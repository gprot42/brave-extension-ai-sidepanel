import { useWebSocket } from '../hooks/useWebSocket';
import { useHealthData } from '../hooks/useHealthData';
import type { HRPoint } from '../types';
import { useState, useEffect, useMemo } from 'react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import InfoTooltip from './InfoTooltip';

interface HRStats {
  avg: number | null;
  min: number | null;
  max: number | null;
  min_ts: string | null;
  max_ts: string | null;
  count: number;
  sleep_rhr: number | null;
  period: string;
}

function hrColor(bpm: number): string {
  if (bpm < 100) return '#34D399';   // green — normal
  if (bpm < 140) return '#FBBF24';   // yellow — elevated
  return '#EF4444';                   // red — high
}

function hrTextClass(bpm: number) {
  if (bpm < 100) return 'text-emerald-400';
  if (bpm < 140) return 'text-yellow-400';
  return 'text-red-400';
}

function hrLabel(bpm: number) {
  if (bpm < 100) return 'Normal';
  if (bpm < 140) return 'Elevated';
  return 'High';
}

export default function RealtimeHR() {
  const { data: wsData } = useWebSocket('/ws/hr');
  const { data: histData } = useHealthData<HRPoint>('/api/hr?limit=300', 3000);
  const [stats, setStats] = useState<HRStats | null>(null);

  useEffect(() => {
    const fetchStats = () =>
      fetch('/api/hr-stats').then(r => r.json()).then(setStats).catch(() => {});
    fetchStats();
    const interval = setInterval(fetchStats, 30000);
    return () => clearInterval(interval);
  }, []);

  const tz = localStorage.getItem('tz') || Intl.DateTimeFormat().resolvedOptions().timeZone;

  const fmtTs = (iso: string | null) => {
    if (!iso) return undefined;
    const d = new Date(iso);
    return d.toLocaleString([], { timeZone: tz, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
  };

  const realtimePoints = wsData.map((d: any) => ({
    time: new Date(d.timestamp).toLocaleTimeString([], { timeZone: tz, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }),
    bpm: d.bpm,
  }));

  const histPoints = [...histData].reverse().map((d) => ({
    time: new Date(d.timestamp).toLocaleTimeString([], { timeZone: tz, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }),
    bpm: d.bpm,
  }));

  const chartData = realtimePoints.length > 0 ? realtimePoints : histPoints;
  const latestBpm = chartData.length > 0 ? chartData[chartData.length - 1].bpm : null;

  const { yMin, yMax } = useMemo(() => {
    if (chartData.length === 0) return { yMin: 50, yMax: 120 };
    const bpms = chartData.map((d: { bpm: number }) => d.bpm);
    return { yMin: Math.min(...bpms) - 5, yMax: Math.max(...bpms) + 5 };
  }, [chartData]);

  // Determine primary line color from latest reading
  const lineColor = latestBpm !== null ? hrColor(latestBpm) : '#34D399';

  return (
    <div className="bg-gray-900 rounded-xl p-3 h-full flex flex-col">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
            Heart Rate<InfoTooltip text="Real-time heart rate from BLE sensor. Green = normal (<100 bpm), Yellow = elevated (100-139), Red = high (140+). Stats show 24h average, min, max, and resting HR during sleep." />
          </h2>
        </div>
        {latestBpm !== null && (
          <div className="flex items-baseline gap-1.5">
            <span className={`text-2xl font-bold ${hrTextClass(latestBpm)}`}>{latestBpm}</span>
            <span className="text-[10px] text-gray-500">bpm</span>
            <span className={`text-[9px] font-medium px-1.5 py-0.5 rounded-full ${
              latestBpm < 100 ? 'bg-emerald-900/40 text-emerald-400' :
              latestBpm < 140 ? 'bg-yellow-900/40 text-yellow-400' :
              'bg-red-900/40 text-red-400'
            }`}>
              {hrLabel(latestBpm)}
            </span>
          </div>
        )}
      </div>

      {/* Stats bar */}
      {stats && stats.avg !== null && (
        <div className="flex gap-1.5 mb-1.5">
          <StatBadge label="Avg" value={stats.avg} unit="bpm" color="#60A5FA" />
          <StatBadge label="Min" value={stats.min} unit="bpm" color="#34D399" tooltip={fmtTs(stats.min_ts)} />
          <StatBadge label="Max" value={stats.max} unit="bpm" color="#EF4444" tooltip={fmtTs(stats.max_ts)} />
          <StatBadge label="Sleep RHR" value={stats.sleep_rhr} unit="bpm" color="#A78BFA" />
        </div>
      )}

      {chartData.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-gray-600 text-xs">
          Waiting for data...
        </div>
      ) : (
        <div className="flex-1 min-h-0" style={{ minHeight: 120 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <XAxis
                dataKey="time"
                tick={{ fontSize: 8, fill: '#6B7280' }}
                interval="preserveStartEnd"
                minTickGap={50}
                axisLine={{ stroke: '#374151' }}
                tickLine={false}
              />
              <YAxis
                domain={[yMin, yMax]}
                tick={{ fontSize: 9, fill: '#6B7280' }}
                width={28}
                axisLine={false}
                tickLine={false}
              />
              {/* Zone reference lines */}
              {yMax >= 100 && (
                <ReferenceLine y={100} stroke="#FBBF24" strokeDasharray="3 3" strokeOpacity={0.3} />
              )}
              {yMax >= 140 && (
                <ReferenceLine y={140} stroke="#EF4444" strokeDasharray="3 3" strokeOpacity={0.3} />
              )}
              <Tooltip
                contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151', borderRadius: 8, fontSize: 11 }}
                formatter={(value: number) => {
                  const color = hrColor(value);
                  return [<span style={{ color }}>{value} bpm ({hrLabel(value)})</span>, 'HR'];
                }}
                labelStyle={{ color: '#9CA3AF' }}
              />
              <Line
                type="monotone"
                dataKey="bpm"
                stroke={lineColor}
                strokeWidth={1.5}
                dot={false}
                activeDot={{ r: 3, fill: lineColor, stroke: '#1F2937', strokeWidth: 2 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

function StatBadge({ label, value, unit, color, tooltip }: {
  label: string;
  value: number | null;
  unit: string;
  color: string;
  tooltip?: string;
}) {
  return (
    <div className="flex-1 bg-gray-800/60 rounded-lg px-2 py-1 text-center relative group" title={tooltip}>
      <div className="text-[8px] text-gray-500 uppercase tracking-wide">{label}</div>
      <div className="text-sm font-bold leading-tight" style={{ color }}>
        {value !== null ? value : '--'}
      </div>
      <div className="text-[7px] text-gray-600">{unit}</div>
      {tooltip && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block bg-gray-700 text-gray-200 text-[9px] px-2 py-0.5 rounded whitespace-nowrap z-10">
          {tooltip}
        </div>
      )}
    </div>
  );
}
