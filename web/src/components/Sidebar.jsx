import { IconLogo, IconUploadCloud, IconList } from '../icons';

const NAV_ITEMS = [
  { label: 'Analyze', icon: IconUploadCloud, active: true },
  { label: 'History', icon: IconList, active: false },
];

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="brand">
        <IconLogo size={26} className="brand-mark" />
        <span className="brand-name">LogSense</span>
      </div>

      <nav className="nav">
        {NAV_ITEMS.map(({ label, icon: Icon, active }) => (
          <div key={label} className={`nav-item${active ? ' active' : ''}`}>
            <Icon size={18} />
            <span>{label}</span>
          </div>
        ))}
      </nav>
    </aside>
  );
}
