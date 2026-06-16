/**
 * SimCore HTTP API client for the Dashboard.
 *
 * All calls go through Vite dev proxy (vite.config.ts) so we can use
 * relative paths like `/api/replay/list` and they'll be forwarded to
 * the SimCore HTTP gateway on port 8000.
 */

export interface ReplayEntry {
  filename: string;
  size_bytes: number;
  modified: number; // unix timestamp
}

export interface ReplayListResponse {
  replays: ReplayEntry[];
}

export interface TickData {
  tick: number;
  entities: Record<string, unknown>;
  resources: Record<string, unknown>;
  is_terminal?: boolean;
  winner?: number;
  map_width?: number;
  map_height?: number;
}

export interface ReplayDetailResponse {
  match_id: string;
  ticks: TickData[];
  tick_count: number;
  player_races?: Record<string, string>;
  winner?: number;
}

export interface LeagueEntry {
  name: string;
  type: string;
  elo: number;
  wins: number;
  losses: number;
  draws: number;
}

export interface LeagueRankingResponse {
  versions: LeagueEntry[];
}

export interface LeagueMatchResult {
  match_id: string;
  winner: number;
  ticks: number;
  tps: number;
}

// ─── API functions ──────────────────────────────────────────────

export async function fetchReplayList(): Promise<ReplayListResponse> {
  const res = await fetch('/api/replay/list');
  if (!res.ok) throw new Error(`replay/list: ${res.status}`);
  return res.json();
}

export async function fetchReplayDetail(matchId: string): Promise<ReplayDetailResponse> {
  const res = await fetch(`/api/replay/${encodeURIComponent(matchId)}`);
  if (!res.ok) throw new Error(`replay/${matchId}: ${res.status}`);
  return res.json();
}

export async function fetchLeagueRanking(): Promise<LeagueRankingResponse> {
  const res = await fetch('/api/league/ranking');
  if (!res.ok) throw new Error(`league/ranking: ${res.status}`);
  return res.json();
}

export async function startLeagueMatch(params: {
  p1_version?: string;
  p2_version?: string;
  map_seed?: number;
  max_ticks?: number;
}): Promise<LeagueMatchResult> {
  const res = await fetch('/api/league/match', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(`league/match: ${res.status}`);
  return res.json();
}

export async function fetchHealth(): Promise<Record<string, unknown>> {
  const res = await fetch('/api/health', { method: 'POST' });
  if (!res.ok) throw new Error(`health: ${res.status}`);
  return res.json();
}
