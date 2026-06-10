import { Link } from 'react-router-dom';

const MOCK_MATCHES = [
  { id: '1', players: ['Agent-Alpha', 'Agent-Beta'], status: 'completed', winner: 1, ticks: 1200 },
  { id: '2', players: ['Agent-Gamma', 'Agent-Delta'], status: 'running', winner: 0, ticks: 450 },
  { id: '3', players: ['Agent-Epsilon', 'Agent-Zeta'], status: 'completed', winner: 2, ticks: 890 },
];

export default function MatchesPage() {
  return (
    <div style={{ maxWidth: 960, margin: '0 auto', padding: '2rem' }}>
      <h1>Matches</h1>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            <th style={thStyle}>ID</th>
            <th style={thStyle}>Players</th>
            <th style={thStyle}>Status</th>
            <th style={thStyle}>Winner</th>
            <th style={thStyle}>Ticks</th>
          </tr>
        </thead>
        <tbody>
          {MOCK_MATCHES.map((m) => (
            <tr key={m.id}>
              <td style={tdStyle}><Link to={`/matches/${m.id}`}>{m.id}</Link></td>
              <td style={tdStyle}>{m.players.join(' vs ')}</td>
              <td style={tdStyle}>{m.status}</td>
              <td style={tdStyle}>{m.winner > 0 ? `P${m.winner}` : '—'}</td>
              <td style={tdStyle}>{m.ticks}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const thStyle: React.CSSProperties = { textAlign: 'left', borderBottom: '2px solid #ddd', padding: 8 };
const tdStyle: React.CSSProperties = { borderBottom: '1px solid #eee', padding: 8 };
