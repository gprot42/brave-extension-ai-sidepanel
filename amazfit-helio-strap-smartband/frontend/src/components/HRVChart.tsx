import { useState, useMemo } from 'react';
import { useHealthData } from '../hooks/useHealthData';
import type { HRVPoint } from '../types';
import {
  ComposedChart, Bar, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Brush, Cell,
} from 'recharts';
import InfoTooltip from './InfoTooltip';

const RANGES = [
  { label: '1h', hours: 1 },
  { label: '6h', hours: 6 },
  { label: '24h', hours: 24 },
  { label: '7d', hours: 168 },
  { label: 'All', hours: 0 },
];

const RMSSD_COLOR = '#22D3EE';  // cyan-400
const SDNN_COLOR = '#F472B6';   // pink-400

/** Downsample data into fixed-width time buckets (avg per bucket). */
function downsample(
  points: { time: string; ts: number; RMSSD: number; SDNN: number }[],
  maxBuckets: number,
) {
  if (points.length <= maxBuckets) return points;

  const bucketSize = Math.ceil(points.length / maxBuckets);
  const result: typeof points = [];

  for (let i = 0; i < points.length; i += bucketSize) {
    const slice = points.slice(i, i + bucketSize);
    const avgRmssd = Math.round(slice.reduce((s, p) => s + p.RMSSD, 0) / slice.length);
    const avgSdnn = Math.round(slice.reduce((s, p) => s + p.SDNN, 0) / slice.length);
    const maxRmssd = Math.max(...slice.map(p => p.RMSSD));
    const minRmssd = Math.min(...slice.map(p => p.RMSSD));
    result.push({
      time: slice[Math.floor(slice.length / 2)].time,
      ts: slice[Math.floor(slice.length / 2)].ts,
      RMSSD: avgRmssd,
      SDNN: avgSdnn,
      // @ts-ignore — extra fields for range display
      rmssdMax: maxRmssd,
      rmssdMin: minRmssd,
    });
  }
  return result;
}

/** Color RMSSD bar by value: low=red, medium=amber, good=cyan, great=green */
function rmssdBarColor(val: number): string {
  if (val < 15) return '#EF4444';   // red — very low
  if (val < 30) return '#FB923C';   // orange — low
  if (val < 60) return '#22D3EE';   // cyan — normal
  return '#34D399';                  // green — excellent
}

export default function HRVChart({ locked, connected }: { locked?: boolean; connected?: boolean }) {
  const { data, loading } = useHealthData<HRVPoint>('/api/hrv', 300000);
  const [range, setRange] = useState('All');
  const tz = localStorage.getItem('tz') || Intl.DateTimeFormat().resolvedOptions().timeZone;

  const { chartData, hasSdnn, avgRmssd, avgSdnn } = useMemo(() => {
    const sorted = [...data].reverse();
    const hours = RANGES.find(r => r.label === range)?.hours || 0;
    const fmt = (ts: string) =>
      new Date(ts).toLocaleTimeString([], { timeZone: tz, hour: '2-digit', minute: '2-digit', hour12: false });

    let filtered = sorted;
    if (hours > 0 && sorted.length > 0) {
      const cutoff = Date.now() - hours * 3600_000;
      filtered = sorted.filter(d => new Date(d.timestamp).getTime() >= cutoff);
    }

    const raw = filtered.map(d => ({
      time: fmt(d.timestamp),
      ts: new Date(d.timestamp).getTime(),
      RMSSD: d.rmssd,
      SDNN: d.sdnn,
    }));

    const hasSdnn = raw.some(d => d.SDNN > 0);
    const ds = downsample(raw, 200);

    const avgRmssd = raw.length > 0
      ? Math.round(raw.reduce((s, p) => s + p.RMSSD, 0) / raw.length)
      : null;
    const avgSdnn = hasSdnn && raw.length > 0
      ? Math.round(raw.reduce((s, p) => s + p.SDNN, 0) / raw.length)
      : null;

    return { chartData: ds, hasSdnn, avgRmssd, avgSdnn };
  }, [data, range, tz]);

  return (
    <div className="bg-gray-900 rounded-xl p-3 h-full flex flex-col">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
            HRV<InfoTooltip text="Heart Rate Variability: RMSSD (beat-to-beat variability) in ms. Higher values indicate better recovery and lower stress. Bars are color-coded: red (<15ms), orange (15-30ms), cyan (30-60ms), green (>60ms)." />
          </h2>
          {avgRmssd !== null && (
            <div className="flex items-center gap-3 ml-1">
              <span className="flex items-center gap-1">
                <span className="text-[10px] text-gray-500">avg</span>
                <span className="text-[10px] font-medium" style={{ color: RMSSD_COLOR }}>
                  {avgRmssd}<span className="text-gray-500">ms</span>
                </span>
              </span>
              {avgSdnn !== null && avgSdnn > 0 && (
                <span className="flex items-center gap-1">
                  <span className="w-3 h-0.5 rounded" style={{ backgroundColor: SDNN_COLOR }} />
                  <span className="text-[10px] font-medium" style={{ color: SDNN_COLOR }}>
                    {avgSdnn}<span className="text-gray-500">ms</span>
                  </span>
                </span>
              )}
            </div>
          )}
        </div>
        {chartData.length > 0 && (
          <div className="flex gap-1">
            {RANGES.map(r => (
              <button
                key={r.label}
                onClick={() => setRange(r.label)}
                className={`px-1.5 py-0.5 text-[9px] rounded ${range === r.label ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-500 hover:text-gray-300'}`}
              >
                {r.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center text-gray-600 text-xs">Loading...</div>
      ) : chartData.length === 0 ? (
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
        <div className="flex-1 min-h-0 flex flex-col">
          <div className="flex-1 min-h-0">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} barCategoryGap="10%">
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 8, fill: '#6B7280' }}
                  interval="preserveStartEnd"
                  minTickGap={40}
                  axisLine={{ stroke: '#374151' }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 9, fill: '#6B7280' }}
                  width={32}
                  axisLine={false}
                  tickLine={false}
                  unit="ms"
                />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151', borderRadius: 8, fontSize: 11 }}
                  labelStyle={{ color: '#9CA3AF', marginBottom: 4 }}
                  formatter={(value: number, name: string) => {
                    const color = name === 'RMSSD' ? rmssdBarColor(value) : SDNN_COLOR;
                    return [<span style={{ color }}>{value} ms</span>, name];
                  }}
                  itemStyle={{ padding: '1px 0' }}
                />
                {/* RMSSD as color-coded bars */}
                <Bar dataKey="RMSSD" radius={[2, 2, 0, 0]} name="RMSSD">
                  {chartData.map((entry, i) => (
                    <Cell key={i} fill={rmssdBarColor(entry.RMSSD)} fillOpacity={0.75} />
                  ))}
                </Bar>
                {/* SDNN as overlay line (only if data exists) */}
                {hasSdnn && (
                  <Line
                    type="monotone"
                    dataKey="SDNN"
                    stroke={SDNN_COLOR}
                    strokeWidth={2}
                    dot={false}
                    name="SDNN"
                  />
                )}
                {chartData.length > 30 && (
                  <Brush
                    dataKey="time"
                    height={16}
                    stroke="#4B5563"
                    fill="#111827"
                    tickFormatter={() => ''}
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="flex justify-center gap-4 mt-0.5">
            <div className="flex items-center gap-3">
              {[
                { label: '<15', color: '#EF4444' },
                { label: '15-30', color: '#FB923C' },
                { label: '30-60', color: '#22D3EE' },
                { label: '60+', color: '#34D399' },
              ].map(({ label, color }) => (
                <div key={label} className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-sm" style={{ backgroundColor: color }} />
                  <span className="text-[8px] text-gray-500">{label}ms</span>
                </div>
              ))}
            </div>
            {hasSdnn && (
              <div className="flex items-center gap-1">
                <svg width="14" height="4"><line x1="0" y1="2" x2="14" y2="2" stroke={SDNN_COLOR} strokeWidth="2" /></svg>
                <span className="text-[8px] text-gray-500">SDNN</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
