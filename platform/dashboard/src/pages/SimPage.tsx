import { useEffect, useRef, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';

/* ── Types ─────────────────────────────────────────────────────────── */

interface SimEntity {
  owner: number;
  entity_type: string;
  unit_type: string;
  building_type: string;
  x: number;
  y: number;
  health: number;
  max_health: number;
  shields: number;
  max_shields: number;
  is_constructing: boolean;
  is_idle: boolean;
  resource_type: string;
  resource_amount: number;
}

interface SimFrame {
  tick: number;
  entities: Record<string, SimEntity>;
  resources: Record<string, number>;
  is_terminal: boolean;
  winner: number;
  map_width: number;
  map_height: number;
}

/* ── Constants ─────────────────────────────────────────────────────── */

const P1_COLOR = '#4FC3F7';   // light blue
const P2_COLOR = '#EF5350';   // red
const NEUTRAL_COLOR = '#BDBDBD'; // grey for resources
const BG_COLOR = '#1a1a2e';
const GRID_COLOR = '#2a2a4a';
const HEALTH_BAR_BG = '#333';
const HEALTH_BAR_FILL_P1 = '#4FC3F7';
const HEALTH_BAR_FILL_P2 = '#EF5350';

const ENTITY_SHAPES: Record<string, 'circle' | 'rect' | 'diamond' | 'triangle'> = {
  worker: 'circle',
  soldier: 'triangle',
  scout: 'diamond',
  building: 'rect',
  resource: 'rect',
};

const ENTITY_SIZES: Record<string, number> = {
  worker: 4,
  soldier: 5,
  scout: 4,
  building: 8,
  resource: 6,
};

/* ── Canvas Renderer ───────────────────────────────────────────────── */

function drawFrame(
  ctx: CanvasRenderingContext2D,
  frame: SimFrame,
  canvasW: number,
  canvasH: number,
) {
  const mapW = frame.map_width || 64;
  const mapH = frame.map_height || 64;
  const scaleX = canvasW / mapW;
  const scaleY = canvasH / mapH;
  const scale = Math.min(scaleX, scaleY);

  // Clear
  ctx.fillStyle = BG_COLOR;
  ctx.fillRect(0, 0, canvasW, canvasH);

  // Grid
  ctx.strokeStyle = GRID_COLOR;
  ctx.lineWidth = 0.5;
  const gridStep = 8;
  for (let gx = 0; gx <= mapW; gx += gridStep) {
    ctx.beginPath();
    ctx.moveTo(gx * scale, 0);
    ctx.lineTo(gx * scale, mapH * scale);
    ctx.stroke();
  }
  for (let gy = 0; gy <= mapH; gy += gridStep) {
    ctx.beginPath();
    ctx.moveTo(0, gy * scale);
    ctx.lineTo(mapW * scale, gy * scale);
    ctx.stroke();
  }

  // Draw entities
  const entities = Object.values(frame.entities);
  // Sort: resources first, then buildings, then units (units on top)
  const order: Record<string, number> = { resource: 0, building: 1, worker: 2, soldier: 3, scout: 4 };
  const sorted = [...entities].sort((a, b) => (order[a.entity_type] ?? 5) - (order[b.entity_type] ?? 5));

  for (const e of sorted) {
    const px = e.x * scale;
    const py = e.y * scale;
    const size = (ENTITY_SIZES[e.entity_type] ?? 4) * scale * 0.12;
    const shape = ENTITY_SHAPES[e.entity_type] ?? 'circle';

    // Color by owner
    let color: string;
    if (e.owner === 1) color = P1_COLOR;
    else if (e.owner === 2) color = P2_COLOR;
    else color = NEUTRAL_COLOR;

    // Dim constructing buildings
    if (e.is_constructing) {
      ctx.globalAlpha = 0.5;
    }

    ctx.fillStyle = color;
    ctx.strokeStyle = '#000';
    ctx.lineWidth = 1;

    switch (shape) {
      case 'circle':
        ctx.beginPath();
        ctx.arc(px, py, size, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
        break;
      case 'rect':
        ctx.fillRect(px - size, py - size, size * 2, size * 2);
        ctx.strokeRect(px - size, py - size, size * 2, size * 2);
        break;
      case 'diamond':
        ctx.beginPath();
        ctx.moveTo(px, py - size);
        ctx.lineTo(px + size, py);
        ctx.lineTo(px, py + size);
        ctx.lineTo(px - size, py);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
        break;
      case 'triangle':
        ctx.beginPath();
        ctx.moveTo(px, py - size);
        ctx.lineTo(px + size, py + size * 0.7);
        ctx.lineTo(px - size, py + size * 0.7);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
        break;
    }

    ctx.globalAlpha = 1.0;

    // Health bar for non-resource, non-dead entities
    if (e.entity_type !== 'resource' && e.max_health > 0) {
      const barW = size * 2.4;
      const barH = 2.5;
      const barX = px - barW / 2;
      const barY = py - size - 5;
      const hpRatio = Math.max(0, e.health / e.max_health);

      ctx.fillStyle = HEALTH_BAR_BG;
      ctx.fillRect(barX, barY, barW, barH);

      ctx.fillStyle = e.owner === 1 ? HEALTH_BAR_FILL_P1 : HEALTH_BAR_FILL_P2;
      ctx.fillRect(barX, barY, barW * hpRatio, barH);

      // Shield bar (if entity has shields)
      if (e.max_shields > 0) {
        const shieldBarY = barY - 3;
        const shieldRatio = Math.max(0, e.shields / e.max_shields);
        ctx.fillStyle = '#7E57C2'; // purple for shields
        ctx.fillRect(barX, shieldBarY, barW * shieldRatio, barH);
      }
    }

    // Resource amount text
    if (e.entity_type === 'resource' && e.resource_amount > 0) {
      ctx.fillStyle = '#fff';
      ctx.font = `${Math.max(8, size * 0.8)}px monospace`;
      ctx.textAlign = 'center';
      ctx.fillText(String(Math.floor(e.resource_amount / 100)), px, py + 3);
    }
  }

  // HUD overlay: tick & resources
  ctx.fillStyle = 'rgba(0,0,0,0.65)';
  ctx.fillRect(0, 0, canvasW, 52);

  ctx.fillStyle = '#fff';
  ctx.font = 'bold 13px monospace';
  ctx.textAlign = 'left';

  const p1Mineral = frame.resources?.p1_mineral ?? 0;
  const p1Gas = frame.resources?.p1_gas ?? 0;
  const p1Supply = `${frame.resources?.p1_supply_used ?? 0}/${frame.resources?.p1_supply_cap ?? 0}`;
  const p2Mineral = frame.resources?.p2_mineral ?? 0;
  const p2Gas = frame.resources?.p2_gas ?? 0;
  const p2Supply = `${frame.resources?.p2_supply_used ?? 0}/${frame.resources?.p2_supply_cap ?? 0}`;

  ctx.fillStyle = P1_COLOR;
  ctx.fillText(`P1  ⛏${p1Mineral}  ⛽${p1Gas}  👥${p1Supply}`, 12, 20);
  ctx.fillStyle = P2_COLOR;
  ctx.fillText(`P2  ⛏${p2Mineral}  ⛽${p2Gas}  👥${p2Supply}`, 12, 40);
  ctx.fillStyle = '#fff';
  ctx.textAlign = 'right';
  ctx.fillText(`Tick: ${frame.tick}`, canvasW - 12, 20);

  if (frame.is_terminal) {
    const winText = frame.winner === 0 ? 'DRAW' : `P${frame.winner} WINS!`;
    ctx.fillStyle = frame.winner === 1 ? P1_COLOR : frame.winner === 2 ? P2_COLOR : '#FFD54F';
    ctx.font = 'bold 16px monospace';
    ctx.textAlign = 'right';
    ctx.fillText(winText, canvasW - 12, 42);
  }
}

/* ── React Component ───────────────────────────────────────────────── */

export default function SimPage() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [frame, setFrame] = useState<SimFrame | null>(null);
  const [connected, setConnected] = useState(false);
  const [simStatus, setSimStatus] = useState<'idle' | 'running'>('idle');
  const [canvasSize, setCanvasSize] = useState({ w: 800, h: 800 });

  // Responsive canvas sizing
  useEffect(() => {
    function onResize() {
      const maxW = Math.min(window.innerWidth - 48, 900);
      const maxH = Math.min(window.innerHeight - 220, 900);
      const s = Math.min(maxW, maxH);
      setCanvasSize({ w: s, h: s });
    }
    onResize();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  // Canvas draw loop — decoupled from React render for perf
  const latestFrame = useRef<SimFrame | null>(null);
  const animIdRef = useRef<number>(0);

  useEffect(() => {
    latestFrame.current = frame;
  }, [frame]);

  useEffect(() => {
    function render() {
      const canvas = canvasRef.current;
      const f = latestFrame.current;
      if (canvas && f) {
        const ctx = canvas.getContext('2d');
        if (ctx) {
          const dpr = window.devicePixelRatio || 1;
          canvas.width = canvasSize.w * dpr;
          canvas.height = canvasSize.h * dpr;
          ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
          drawFrame(ctx, f, canvasSize.w, canvasSize.h);
        }
      }
      animIdRef.current = requestAnimationFrame(render);
    }
    animIdRef.current = requestAnimationFrame(render);
    return () => cancelAnimationFrame(animIdRef.current);
  }, [canvasSize]);

  // Check sim status on mount
  useEffect(() => {
    fetch('/api/sim/status')
      .then(r => r.json())
      .then(d => setSimStatus(d.status === 'running' ? 'running' : 'idle'))
      .catch(() => setSimStatus('idle'));
  }, []);

  // WebSocket connection
  const connectWs = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const host = window.location.host;
    const wsUrl = `${protocol}://${host}/api/sim/ws`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      setConnected(true);
      // If a sim is already running, we'll start receiving frames from the runner
    };

    ws.onmessage = (ev) => {
      try {
        const data: SimFrame = JSON.parse(ev.data);
        setFrame(data);
        if (data.is_terminal) setSimStatus('idle');
      } catch {
        // ignore malformed frames
      }
    };

    ws.onclose = () => {
      setConnected(false);
      // Auto-reconnect after 2s
      setTimeout(connectWs, 2000);
    };

    ws.onerror = () => {
      ws.close();
    };

    wsRef.current = ws;
  }, []);

  useEffect(() => {
    connectWs();
    return () => {
      wsRef.current?.close();
    };
  }, [connectWs]);

  // Start a new battle
  async function handleStart() {
    try {
      const res = await fetch('/api/sim/start', { method: 'POST' });
      if (res.ok) {
        setSimStatus('running');
        // Send start via WS too so runner adds us as client
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ action: 'start', params: {} }));
        }
      }
    } catch (e: any) {
      console.error('Failed to start sim:', e);
    }
  }

  // Stop the battle
  async function handleStop() {
    try {
      await fetch('/api/sim/stop', { method: 'POST' });
      setSimStatus('idle');
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ action: 'stop' }));
      }
    } catch (e: any) {
      console.error('Failed to stop sim:', e);
    }
  }

  const tick = frame?.tick ?? 0;
  const isTerminal = frame?.is_terminal ?? false;
  const winner = frame?.winner ?? 0;

  return (
    <div style={{ maxWidth: 960, margin: '0 auto', padding: '1.5rem', fontFamily: 'system-ui, sans-serif' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <Link to="/" style={{ color: '#1a73e8', fontSize: 13, display: 'inline-block', marginBottom: 8 }}>
            ← Back to dashboard
          </Link>
          <h1 style={{ margin: 0, fontSize: 22 }}>🎮 SimCore Live Battle</h1>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <span style={{
            fontSize: 12,
            padding: '3px 10px',
            borderRadius: 12,
            background: connected ? '#E8F5E9' : '#FFEBEE',
            color: connected ? '#2E7D32' : '#C62828',
            fontWeight: 600,
          }}>
            {connected ? '● Connected' : '○ Disconnected'}
          </span>
          <button
            onClick={simStatus === 'running' ? handleStop : handleStart}
            style={{
              padding: '8px 22px',
              background: simStatus === 'running' ? '#EF5350' : '#43A047',
              color: '#fff',
              border: 'none',
              borderRadius: 6,
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: 14,
            }}
          >
            {simStatus === 'running' ? '⏹ Stop' : '▶ Start Battle'}
          </button>
        </div>
      </div>

      {/* Canvas */}
      <div style={{
        background: '#0d0d1a',
        borderRadius: 10,
        padding: 8,
        display: 'flex',
        justifyContent: 'center',
        boxShadow: '0 4px 24px rgba(0,0,0,0.5)',
      }}>
        <canvas
          ref={canvasRef}
          style={{
            width: canvasSize.w,
            height: canvasSize.h,
            borderRadius: 6,
            display: 'block',
          }}
        />
      </div>

      {/* Info bar */}
      <div style={{
        marginTop: 12,
        display: 'flex',
        justifyContent: 'space-between',
        fontSize: 13,
        color: '#888',
      }}>
        <span>Tick: <b style={{ color: '#fff' }}>{tick}</b></span>
        <span>
          {isTerminal
            ? (winner === 0 ? '🤝 Draw' : `🏆 P${winner} Wins!`)
            : (simStatus === 'running' ? '⚡ Live' : '⏸ Idle')}
        </span>
        <span>Entities: <b style={{ color: '#fff' }}>{frame ? Object.keys(frame.entities).length : 0}</b></span>
      </div>

      {/* Legend */}
      <div style={{
        marginTop: 16,
        background: '#1e1e2e',
        borderRadius: 8,
        padding: 14,
        fontSize: 12,
        display: 'flex',
        gap: 24,
        flexWrap: 'wrap' as const,
      }}>
        <LegendItem color={P1_COLOR} shape="circle" label="P1 Unit" />
        <LegendItem color={P2_COLOR} shape="circle" label="P2 Unit" />
        <LegendItem color={P1_COLOR} shape="rect" label="P1 Building" />
        <LegendItem color={P2_COLOR} shape="rect" label="P2 Building" />
        <LegendItem color={NEUTRAL_COLOR} shape="rect" label="Resource" />
        <LegendItem color={P1_COLOR} shape="triangle" label="P1 Soldier" />
        <LegendItem color={P2_COLOR} shape="triangle" label="P2 Soldier" />
        <LegendItem color={P1_COLOR} shape="diamond" label="P1 Scout" />
        <LegendItem color={P2_COLOR} shape="diamond" label="P2 Scout" />
      </div>
    </div>
  );
}

/* ── Helper components ─────────────────────────────────────────────── */

function LegendItem({ color, shape, label }: { color: string; shape: string; label: string }) {
  const size = 8;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <svg width={size * 2 + 4} height={size * 2 + 4} style={{ display: 'block' }}>
        {shape === 'circle' && (
          <circle cx={size + 2} cy={size + 2} r={size} fill={color} stroke="#000" strokeWidth={1} />
        )}
        {shape === 'rect' && (
          <rect x={2} y={2} width={size * 2} height={size * 2} fill={color} stroke="#000" strokeWidth={1} />
        )}
        {shape === 'triangle' && (
          <polygon points={`${size + 2},2 ${size * 2 + 2},${size * 2 + 2} 2,${size * 2 + 2}`} fill={color} stroke="#000" strokeWidth={1} />
        )}
        {shape === 'diamond' && (
          <polygon points={`${size + 2},2 ${size * 2 + 2},${size + 2} ${size + 2},${size * 2 + 2} 2,${size + 2}`} fill={color} stroke="#000" strokeWidth={1} />
        )}
      </svg>
      <span style={{ color: '#ccc' }}>{label}</span>
    </div>
  );
}
