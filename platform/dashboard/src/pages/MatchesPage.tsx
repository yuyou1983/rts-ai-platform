import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchReplayList, fetchLeagueRanking, startLeagueMatch, type ReplayEntry, type LeagueEntry } from '../api';

function Nav() {
  return (
    <nav style={{ display: 'flex', gap: 18, marginBottom: 10, fontSize: 14 }}>
      <Link to="/" style={{ color: '#1a73e8', fontWeight: 600 }}>📼 Matches</Link>
      <Link to="/sim" style={{ color: '#1a73e8', fontWeight: 600 }}>🎮 Live Sim</Link>
    </nav>
  );
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}

function extractMatchId(filename: string): string {
  return filename.replace(/\.(jsonl?|json)$/, '');
}

export default function MatchesPage() {
  const [replays, setReplays] = useState<ReplayEntry[]>([]);
  const [ranking, setRanking] = useState<LeagueEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [matchRunning, setMatchRunning] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const [r, l] = await Promise.allSettled([
          fetchReplayList(),
          fetchLeagueRanking(),
        ]);
        if (r.status === 'fulfilled') setReplays(r.value.replays);
        else setError(prev => prev + (prev ? ' | ' : '') + `Replays: ${r.reason}`);
        if (l.status === 'fulfilled') setRanking(l.value.versions);
      } catch (e: any) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    }
    load();
    // Refresh every 10s
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, []);

  async function handleRunMatch() {
    setMatchRunning(true);
    try {
      await startLeagueMatch({});
      // Refresh data after match
      const [r, l] = await Promise.all([fetchReplayList(), fetchLeagueRanking()]);
      setReplays(r.replays);
      setRanking(l.versions);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setMatchRunning(false);
    }
  }

  if (loading) return <div style={{ padding: 32 }}>Loading…</div>;

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '2rem', fontFamily: 'system-ui, sans-serif' }}>
      <Nav />
      <h1 style={{ marginBottom: 8 }}>⚔️ RTS-AI Platform</h1>
      <p style={{ color: '#666', marginBottom: 24 }}>Real-time strategy AI research &amp; visualization</p>

      {/* Quick Actions */}
      <div style={{ marginBottom: 24, display: 'flex', gap: 12 }}>
        <button
          onClick={handleRunMatch}
          disabled={matchRunning}
          style={{
            padding: '8px 20px',
            background: matchRunning ? '#ccc' : '#1a73e8',
            color: '#fff',
            border: 'none',
            borderRadius: 6,
            cursor: matchRunning ? 'wait' : 'pointer',
            fontWeight: 600,
          }}
        >
          {matchRunning ? '🔄 Running Match…' : '▶ Run League Match'}
        </button>
      </div>

      {error && (
        <div style={{ padding: 12, background: '#fff3cd', borderRadius: 6, marginBottom: 16, fontSize: 13 }}>
          ⚠️ API Error: {error} — Is the SimCore gateway running on port 8000?
        </div>
      )}

      {/* League Ranking */}
      {ranking.length > 0 && (
        <div style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 18, marginBottom: 12 }}>🏆 League Ranking</h2>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr>
                <th style={thStyle}>#</th>
                <th style={thStyle}>Agent</th>
                <th style={thStyle}>ELO</th>
                <th style={thStyle}>W</th>
                <th style={thStyle}>L</th>
                <th style={thStyle}>D</th>
                <th style={thStyle}>Win Rate</th>
              </tr>
            </thead>
            <tbody>
              {ranking
                .sort((a, b) => b.elo - a.elo)
                .map((entry, i) => {
                  const total = entry.wins + entry.losses + entry.draws;
                  const wr = total > 0 ? ((entry.wins / total) * 100).toFixed(1) : '—';
                  return (
                    <tr key={entry.name}>
                      <td style={tdStyle}>{i + 1}</td>
                      <td style={tdStyle}><b>{entry.name}</b></td>
                      <td style={{ ...tdStyle, fontFamily: 'monospace' }}>{entry.elo.toFixed(0)}</td>
                      <td style={{ ...tdStyle, color: '#2e7d32' }}>{entry.wins}</td>
                      <td style={{ ...tdStyle, color: '#c62828' }}>{entry.losses}</td>
                      <td style={tdStyle}>{entry.draws}</td>
                      <td style={tdStyle}>{wr}%</td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      )}

      {/* Replay History */}
      <div>
        <h2 style={{ fontSize: 18, marginBottom: 12 }}>📼 Replay History</h2>
        {replays.length === 0 ? (
          <p style={{ color: '#999', fontStyle: 'italic' }}>No replays yet. Run a match to create one.</p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr>
                <th style={thStyle}>Match ID</th>
                <th style={thStyle}>Size</th>
                <th style={thStyle}>Date</th>
              </tr>
            </thead>
            <tbody>
              {replays.map((r) => (
                <tr key={r.filename}>
                  <td style={tdStyle}>
                    <Link to={`/matches/${extractMatchId(r.filename)}`} style={{ color: '#1a73e8' }}>
                      {extractMatchId(r.filename)}
                    </Link>
                  </td>
                  <td style={{ ...tdStyle, fontFamily: 'monospace' }}>
                    {(r.size_bytes / 1024).toFixed(1)} KB
                  </td>
                  <td style={tdStyle}>{formatTime(r.modified)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

const thStyle: React.CSSProperties = { textAlign: 'left', borderBottom: '2px solid #ddd', padding: 8 };
const tdStyle: React.CSSProperties = { borderBottom: '1px solid #eee', padding: 8 };
