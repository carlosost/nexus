/**
 * Application entry point — lightweight client-side router.
 *
 * Routes:
 *   /                    → Dashboard  (read-only application inventory)
 *   /settings            → Settings   (Jobs / Candidates / Applications admin)
 *   /review/:id          → ReviewApp  (human-in-the-loop score review)
 *
 * No external router library required — path matching covers the three
 * distinct views the application currently needs.
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import Dashboard from './components/Dashboard.jsx';
import Settings  from './components/Settings.jsx';
import ReviewApp from './components/ReviewApp.jsx';
import './styles/dashboard.css';

function Router() {
  const parts = window.location.pathname.split('/').filter(Boolean);

  // /settings
  if (parts[0] === 'settings') {
    return <Settings />;
  }

  // /review/:applicationId
  if (parts[0] === 'review' && parts[1]) {
    return <ReviewApp applicationId={parts[1]} />;
  }

  // / or anything else → Dashboard
  return <Dashboard />;
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Router />
  </StrictMode>
);
