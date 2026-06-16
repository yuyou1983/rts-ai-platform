import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from 'recharts';
import { fetchReplayDetail, type TickData } from '../api';

interface ResourcePoint {
  tick: number;
  p1_minerals: number;
  p1_gas: number;
  p1_supply_used: number;
  p1_supply_cap: number;
  p2_minerals: number;
  p2_gas: number;
  p2_supply_used: number;
  p2_supply_cap: number;
}

function extractResources(ticks: TickData[]): ResourcePoint[] {
  // Sample every ~20 ticks to keep chart performant
  const step = Math.max(1, Math.floor(ticks.length / 200));
  const points: ResourcePoint[] = [];
  for (let i = 0; i < ticks.length; i += step) {
    const t = ticks[i];
    const res = t.resources || {};
    const p1 = (res as any)['1'] || (res as any).p1 || {};
    const p2 = (res as any)['2'] || (res as any).p2 || {};
    points.push({
      tick: t.tick ?? i,
      p1_minerals: p1.minerals ?? p1.mineral ?? 0,
      p1_gas: p1.gas ?? 0,
      p1_supply_used: p1.supply_used ?? 0,
      p1_supply_cap: p1.supply_cap ?? 0,
      p2_minerals: p2.minerals ?? p2.mineral ?? 0,
      p2_gas: p2.gas ?? 0,
      p2_supply_used: p2.supply_used ?? 0,
      p2_supply_cap: p2.supply_cap ?? 0,
    });
  }
  return points;
}

function countEntities(ticks: TickData[]): { tick: number; p1_units: number; p2_units: number; p1_buildings: number; p2_buildings: number }[] {
  const step = Math.max(1, Math.floor(ticks.length / 200));
  const points: any[] = [];
  for (let i = 0; i < ticks.length; i += step) {
    const t = ticks[i];
    const ents = t.entities || {};
    const entries = Object.values(ents) as any[];
    let p1u = 0, p2u = 0, p1b = 0, p2b = 0;
    for (const e of entries) {
      if (e.entity_type === 'worker' || e.entity_type === 'soldier' || e.entity_type === 'scout') {
        if (e.owner === 1) p1u++; else if (e.owner === 2) p2u++;
      }
      if (e.entity_type === 'building') {
        if (e.owner === 1) p1b++; else if (e.owner === 2) p2b++;
      }
    }
    points.push({ tick: t.tick ?? i, p1_units: p1u, p2_units: p2u, p1_buildings: p1b, p2_buildings: p2b });
  }
  return points;
}

const COLORS = {
  p1: '#2196F3',  // blue
  p2: '#F44336',  // red
  gas1: '#795548', gas2: '#8D6E63',
};

export default function MatchDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<{ ticks: TickData[]; tick_count: number; winner?: number; player_races?: Record<string, string> } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedTick, setSelectedTick] = useState(0);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    fetchReplayDetail(id)
      .then(d => {
        setData(d);
        setSelectedTick(d.tick_count - 1);
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div style={{ padding: 32 }}>Loading replay…</div>;
  if (error) return <div style={{ padding: 32, color: 'red' }}>Error: {error}</div>;
  if (!data) return null;

  const resourceData = extractResources(data.ticks);
  const entityData = countEntities(data.ticks);
  const winnerLabel = data.winner
    ? `P${data.winner} (${data.player_races?.[String(data.winner)] ?? '?'})`
    : 'Draw';
  const p1Race = data.player_races?.['1'] ?? 'Terran';
  const p2Race = data.player_races?.['2'] ?? 'Zerg';

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '2rem', fontFamily: 'system-ui, sans-serif' }}>
      <Link to="/" style={{ color: '#1a73e8', marginBottom: 16, display: 'inline-block' }}>
        ← Back to matches
      </Link>

      <h1 style={{ marginBottom: 8 }}>Match {id}</h1>
      <div style={{ fontSize: 14, color: '#555', marginBottom: 20 }}>
        <span>🏆 <b>{winnerLabel}</b> wins</span>
        &nbsp;·&nbsp;
        <span>🕐 {data.tick_count} ticks</span>
        &nbsp;·&nbsp;
        <span>👥 P1({p1Race}) vs P2({p2Race})</span>
      </div>

      {/* Tick Scrubber */}
      <div style={{ marginBottom: 24 }}>
        <label style={{ fontSize: 13, color: '#666' }}>
          Tick: <b>{selectedTick}</b> / {data.tick_count - 1}
        </label>
        <input
          type="range"
          min={0}
          max={data.tick_count - 1}
          value={selectedTick}
          onChange={e => setSelectedTick(Number(e.target.value))}
          style={{ width: '100%', marginTop: 4 }}
        />
      </div>

      {/* Resource Chart */}
      <div style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: 16, marginBottom: 8 }}>💎 Resources</h2>
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={resourceData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="tick" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Area type="monotone" dataKey="p1_minerals" stroke={COLORS.p1} fill={COLORS.p1} fillOpacity={0.1} name={`P1(${p1Race}) Minerals`} />
            <Area type="monotone" dataKey="p2_minerals" stroke={COLORS.p2} fill={COLORS.p2} fillOpacity={0.1} name={`P2(${p2Race}) Minerals`} />
            <Area type="monotone" dataKey="p1_gas" stroke={COLORS.gas1} fill={COLORS.gas1} fillOpacity={0.1} name={`P1(${p1Race}) Gas`} />
            <Area type="monotone" dataKey="p2_gas" stroke={COLORS.gas2} fill={COLORS.gas2} fillOpacity={0.1} name={`P2(${p2Race}) Gas`} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Army / Building Chart */}
      <div style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: 16, marginBottom: 8 }}>⚔️ Army & Buildings</h2>
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={entityData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="tick" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Area type="monotone" dataKey="p1_units" stroke={COLORS.p1} fill={COLORS.p1} fillOpacity={0.1} name={`P1(${p1Race}) Units`} />
            <Area type="monotone" dataKey="p2_units" stroke={COLORS.p2} fill={COLORS.p2} fillOpacity={0.1} name={`P2(${p2Race}) Units`} />
            <Area type="monotone" dataKey="p1_buildings" stroke={COLORS.p1} strokeDasharray="5 5" fill="none" name={`P1(${p1Race}) Buildings`} />
            <Area type="monotone" dataKey="p2_buildings" stroke={COLORS.p2} strokeDasharray="5 5" fill="none" name={`P2(${p2Race}) Buildings`} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Raw Tick Snapshot */}
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 16, marginBottom: 8 }}>📋 Tick {selectedTick} Snapshot</h2>
        <pre style={{
          background: '#1e1e1e', color: '#d4d4d4', padding: 16,
          borderRadius: 8, fontSize: 12, maxHeight: 400, overflow: 'auto',
        }}>
          {JSON.stringify(data.ticks[selectedTick] ?? {}, null, 2)}
        </pre>
      </div>
    </div>
  );
}
