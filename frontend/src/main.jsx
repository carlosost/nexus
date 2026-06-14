import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import ReviewApp from './components/ReviewApp.jsx';

// Application ID is read from the URL: /review/:applicationId
const pathParts = window.location.pathname.split('/').filter(Boolean);
const applicationId = pathParts[pathParts.indexOf('review') + 1] || null;

function Root() {
  const [input, setInput] = useState('');

  if (applicationId) {
    return <ReviewApp applicationId={applicationId} />;
  }

  function handleSubmit(e) {
    e.preventDefault();
    const uuid = input.trim();
    if (uuid) window.location.href = `/review/${uuid}`;
  }

  return (
    <main style={{ fontFamily: 'sans-serif', maxWidth: 480, margin: '80px auto', padding: '0 16px' }}>
      <h1>Resume Review</h1>
      <p>Enter an application UUID to open its review page.</p>
      <form onSubmit={handleSubmit} style={{ display: 'flex', gap: 8 }}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
          style={{ flex: 1, padding: '8px 12px', fontSize: 14, fontFamily: 'monospace' }}
          autoFocus
        />
        <button type="submit" style={{ padding: '8px 16px' }}>Open</button>
      </form>
    </main>
  );
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Root />
  </StrictMode>
);
