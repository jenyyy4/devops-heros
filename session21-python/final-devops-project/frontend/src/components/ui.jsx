import { STATUS_LABELS, initials } from '../lib/schedule.js';

export function StatusBadge({ status }) {
  return <span className={`badge status-${status.toLowerCase()}`}>{STATUS_LABELS[status]}</span>;
}

export function Avatar({ name, tone = 'teal' }) {
  return <span className={`avatar avatar-${tone}`} aria-hidden="true">{initials(name)}</span>;
}

export function Kpi({ label, value, hint, tone }) {
  return (
    <div className={`kpi kpi-${tone}`}>
      <small>{label}</small>
      <strong>{value}</strong>
      <span>{hint}</span>
    </div>
  );
}

export function Modal({ title, eyebrow, onClose, children }) {
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="modal-head">
          <div>
            <p className="eyebrow">{eyebrow}</p>
            <h2>{title}</h2>
          </div>
          <button type="button" className="close" onClick={onClose} aria-label="Close">×</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Empty({ children }) {
  return <div className="empty">{children}</div>;
}
