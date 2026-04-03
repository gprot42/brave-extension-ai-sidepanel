import { useHealthData } from '../hooks/useHealthData';
import type { ActivityEntry } from '../types';
import InfoTooltip from './InfoTooltip';

export default function ActivitySummary({ locked, connected }: { locked?: boolean; connected?: boolean }) {
  const { data, loading } = useHealthData<ActivityEntry>('/api/activity?limit=7', 30000);

  const today = data.length > 0 ? data[0] : null;

  return (
    <div className="bg-gray-900 rounded-xl p-3 h-full flex flex-col">
      <h2 className="text-xs font-semibold mb-2 text-gray-400 uppercase tracking-wide">Activity<InfoTooltip text="Daily steps and calories from device. Steps are synced from the device's daily summary via ECDH-authenticated fetch. Calories update in real-time from the sensor stream." /></h2>
      {loading ? (
        <div className="flex-1 flex items-center justify-center text-gray-600 text-xs">Loading...</div>
      ) : !today ? (
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
            <span>No activity data yet</span>
            <span className="text-[10px]">Click Sync to fetch from device</span>
          </div>
        )
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 mb-3">
            <div className="text-center">
              <div className="text-xl font-bold text-blue-400">{today.steps.toLocaleString()}</div>
              <div className="text-[10px] text-gray-500">Steps</div>
            </div>
            <div className="text-center">
              <div className="text-xl font-bold text-orange-400">{today.calories.toLocaleString()}</div>
              <div className="text-[10px] text-gray-500">Calories</div>
            </div>
          </div>
          <div className="flex-1 overflow-auto space-y-0.5">
            {[...data].reverse().map((d) => (
              <div key={d.date} className="flex justify-between text-xs text-gray-400">
                <span>{d.date.slice(5)}</span>
                <span>{d.steps.toLocaleString()} steps / {d.calories.toLocaleString()} cal</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
