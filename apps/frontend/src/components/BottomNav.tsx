import { NavLink } from 'react-router-dom';

export function BottomNav() {
  return <nav className="bottom-nav" aria-label="Main navigation"><NavLink to="/">Alerts</NavLink><NavLink to="/map">Map</NavLink><NavLink to="/actions">Actions</NavLink><NavLink to="/report">Report</NavLink></nav>;
}
