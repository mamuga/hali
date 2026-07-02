import { Route, Routes } from 'react-router-dom';
import { BottomNav } from './components/BottomNav';
import { ActionCard } from './pages/ActionCard';
import { AlertFeed } from './pages/AlertFeed';
import { MapView } from './pages/MapView';
import { Offline } from './pages/Offline';
import { ReportForm } from './pages/ReportForm';

export function App() {
  return <><Routes><Route path="/" element={<AlertFeed />} /><Route path="/map" element={<MapView />} /><Route path="/actions" element={<ActionCard />} /><Route path="/report" element={<ReportForm />} /><Route path="/offline" element={<Offline />} /></Routes><BottomNav /></>;
}
