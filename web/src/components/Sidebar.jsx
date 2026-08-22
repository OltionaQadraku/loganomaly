import { IconLogo, IconUploadCloud, IconList } from '../icons';

const NAV_ITEMS = [
  { id: 'analyze', label: 'Analyze', icon: IconUploadCloud },
  { id: 'history', label: 'History', icon: IconList },
];

export default function Sidebar({ view, onNavigate, user, onLogout }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <IconLogo size={26} className="brand-mark" />
        <span className="brand-name">LogSense</span>
      </div>

      <nav className="nav">
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            className={`nav-item${view === id ? ' active' : ''}`}
            onClick={() => onNavigate(id)}
          >
            <Icon size={18} />
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        <span className="sidebar-username">{user?.username}</span>
        <button type="button" className="link-button" onClick={onLogout}>
          Log out
        </button>
      </div>
    </aside>
  );
}
