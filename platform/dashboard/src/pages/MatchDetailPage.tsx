import { useParams, Link } from 'react-router-dom';

const MOCK_TICK = {
  tick: 0,
  entities: { units: [], buildings: [] },
  resources: { p1: { gold: 500, wood: 300 }, p2: { gold: 500, wood: 300 } },
  is_terminal: false,
  winner: 0,
};

export default function MatchDetailPage() {
  const { id } = useParams<{ id: string }>();

  return (
    <div style={{ maxWidth: 960, margin: '0 auto', padding: '2rem' }}>
      <Link to="/">← Back to matches</Link>
      <h1>Match {id}</h1>
      <p>Match detail page — charts and replay viewer will go here.</p>
      <pre style={{ background: '#eee', padding: 16, borderRadius: 8 }}>
        {JSON.stringify(MOCK_TICK, null, 2)}
      </pre>
    </div>
  );
}
