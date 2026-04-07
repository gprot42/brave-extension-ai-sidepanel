import { useHealthData } from '../hooks/useHealthData';
import type { StressPoint } from '../types';
import {
  XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  BarChart, Bar,
} from 'recharts';
import InfoTooltip from './InfoTooltip';

function stressColor(level: number): string {
  if (level <= 25) return '#34D399'; // green
  if (level <= 50) return '#FBBF24'; // yellow
  if (level <= 75) return '#FB923C'; // orange
  return '#EF4444'; // red
}

export default function StressChart() {
  const { data, loading } = useHealthData<StressPoint>('/api/stress', 300000);

  const chartData = [...data].reverse().map((d) => ({
    time: new Date(d.timestamp).toLocaleTimeString(),
    level: d.level,
    fill: stressColor(d.level),
  }));

  const latest = data.length > 0 ? data[0].level : null;
  const latestColor = latest !== null ? stressColor(latest) : '#6B7280';

  return (
    <div className="bg-gray-900 rounded-xl p-3 h-full flex flex-col">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Stress<InfoTooltip text="Stress level 0-100 measured per minute. Lower is better. Based on heart rate variability analysis. The Helio Strap may not actively compute stress — data depends on device firmware." /></h2>
        {latest !== null && <span className="text-lg font-bold" style={{ color: latestColor }}>{latest}<span className="text-xs text-gray-500 font-normal"> / 100</span></span>}
      </div>
      {loading ? (
        <div className="flex-1 flex items-center justify-center text-gray-600 text-xs">Loading...</div>
      ) : chartData.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center text-gray-600 gap-2">
          <div className="flex items-center gap-3">
            {[
              { label: 'Relaxed', range: '0-25', color: '#34D399' },
              { label: 'Normal', range: '26-50', color: '#FBBF24' },
              { label: 'Medium', range: '51-75', color: '#FB923C' },
              { label: 'High', range: '76-100', color: '#EF4444' },
            ].map(({ label, range, color }) => (
              <div key={label} className="flex flex-col items-center gap-0.5">
                <div className="w-6 h-6 rounded-full flex items-center justify-center" style={{ backgroundColor: color + '20', border: `1.5px solid ${color}40` }}>
                  <span className="text-[8px] font-bold" style={{ color }}>{range.split('-')[0]}</span>
                </div>
                <span className="text-[8px] text-gray-600">{label}</span>
                <span className="text-[7px] text-gray-700">{range}</span>
              </div>
            ))}
          </div>
          <div className="text-center">
            <span className="text-[10px] text-gray-600 block">No stress data recorded</span>
            <span className="text-[9px] text-gray-700">This device may not support continuous stress measurement</span>
          </div>
        </div>
      ) : (
        <div className="flex-1 min-h-0">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} barCategoryGap={0} barGap={0}>
              <XAxis dataKey="time" tick={false} axisLine={false} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 9, fill: '#6B7280' }} width={25} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1F2937', border: 'none', borderRadius: 6, fontSize: 11 }}
                formatter={(value: number) => {
                  const c = stressColor(value);
                  return [<span style={{ color: c }}>{value} / 100</span>, 'Stress'];
                }}
              />
              <Bar dataKey="level" radius={[1, 1, 0, 0]}>
                {chartData.map((entry, i) => (
                  <Cell key={i} fill={entry.fill} fillOpacity={0.8} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
