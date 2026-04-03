import { useState, useMemo } from 'react';
import { useHealthData } from '../hooks/useHealthData';
import type { SpO2Point } from '../types';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Brush,
} from 'recharts';
import InfoTooltip from './InfoTooltip';

function spo2Color(value: number): string {
  if (value >= 95) return '#34D399';
  if (value >= 90) return '#FBBF24';
  return '#EF4444';
}

function spo2TextClass(value: number): string {
  if (value >= 95) return 'text-emerald-400';
  if (value >= 90) return 'text-yellow-400';
  return 'text-red-400';
}

function CustomDot(props: any) {
  const { cx, cy, payload } = props;
  if (cx == null || cy == null) return null;
  return <circle cx={cx} cy={cy} r={2.5} fill={spo2Color(payload.value)} stroke="none" />;
}

function CustomActiveDot(props: any) {
  const { cx, cy, payload } = props;
  if (cx == null || cy == null) return null;
  return <circle cx={cx} cy={cy} r={4} fill={spo2Color(payload.value)} stroke="#1F2937" strokeWidth={2} />;
}

const RANGES = [
  { label: '1h', hours: 1 },
  { label: '6h', hours: 6 },
  { label: '24h', hours: 24 },
  { label: '7d', hours: 168 },
  { label: 'All', hours: 0 },
];

export default function SpO2Chart({ locked, connected }: { locked?: boolean; connected?: boolean }) {
  const { data, loading } = useHealthData<SpO2Point>('/api/spo2', 300000);
  const [range, setRange] = useState('All');
  const tz = localStorage.getItem('tz') || Intl.DateTimeFormat().resolvedOptions().timeZone;

  const chartData = useMemo(() => {
    const sorted = [...data].reverse();
    const hours = RANGES.find(r => r.label === range)?.hours || 0;
    if (hours === 0 || sorted.length === 0) {
      return sorted.map(d => ({
        ts: new Date(d.timestamp).getTime(),
        time: new Date(d.timestamp).toLocaleTimeString([], { timeZone: tz, hour: '2-digit', minute: '2-digit', hour12: false }),
        value: d.value,
      }));
    }
    const cutoff = Date.now() - hours * 3600_000;
    return sorted
      .filter(d => new Date(d.timestamp).getTime() >= cutoff)
      .map(d => ({
        ts: new Date(d.timestamp).getTime(),
        time: new Date(d.timestamp).toLocaleTimeString([], { timeZone: tz, hour: '2-digit', minute: '2-digit', hour12: false }),
        value: d.value,
      }));
  }, [data, range, tz]);

  const latest = data.length > 0 ? data[0].value : null;
  const showDots = chartData.length < 200;

  return (
    <div className="bg-gray-900 rounded-xl p-3 h-full flex flex-col">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
          SpO2<InfoTooltip text="Blood oxygen saturation (%). Green: 95-100% (normal). Yellow: 90-94% (concerning). Red: below 90% (seek medical attention). Use time buttons or drag the slider to zoom." />
        </h2>
        <div className="flex items-center gap-2">
          {latest !== null && (
            <span className={`text-lg font-bold ${spo2TextClass(latest)}`}>{latest}%</span>
          )}
        </div>
      </div>

      {/* Time range buttons */}
      {chartData.length > 0 && (
        <div className="flex gap-1 mb-1">
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
        <div className="flex-1 min-h-0">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <defs>
                <linearGradient id="spo2Gradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#34D399" />
                  <stop offset="33%" stopColor="#34D399" />
                  <stop offset="50%" stopColor="#FBBF24" />
                  <stop offset="75%" stopColor="#EF4444" />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="time"
                tick={{ fontSize: 8, fill: '#6B7280' }}
                interval="preserveStartEnd"
                minTickGap={40}
              />
              <YAxis domain={[85, 100]} tick={{ fontSize: 9, fill: '#6B7280' }} width={25} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1F2937', border: 'none', borderRadius: 6, fontSize: 11 }}
                formatter={(value: number) => {
                  const label = value >= 95 ? 'Normal' : value >= 90 ? 'Low' : 'Critical';
                  return [`${value}% (${label})`, 'SpO2'];
                }}
                labelStyle={{ color: '#9CA3AF' }}
              />
              <ReferenceLine y={95} stroke="#FBBF24" strokeDasharray="3 3" strokeOpacity={0.5} />
              <ReferenceLine y={90} stroke="#EF4444" strokeDasharray="3 3" strokeOpacity={0.5} />
              <Line
                type="monotone"
                dataKey="value"
                stroke="url(#spo2Gradient)"
                strokeWidth={1.5}
                dot={showDots ? <CustomDot /> : false}
                activeDot={<CustomActiveDot />}
              />
              {chartData.length > 20 && (
                <Brush
                  dataKey="time"
                  height={16}
                  stroke="#4B5563"
                  fill="#111827"
                  tickFormatter={() => ''}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
          <div className="flex justify-center gap-3 mt-0.5">
            <div className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
              <span className="text-[8px] text-gray-500">95-100%</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-yellow-400" />
              <span className="text-[8px] text-gray-500">90-94%</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-red-400" />
              <span className="text-[8px] text-gray-500">&lt;90%</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
