import { useState } from 'react';
import { STATUSES, STATUS_LABELS, endTime, formatTime, nextActions, upNext } from '../lib/schedule.js';
import { Avatar, Empty, Kpi, StatusBadge } from '../components/ui.jsx';

export default function Today({ stats, appointments, loading, onStatus }) {
  const [filter, setFilter] = useState('ALL');
  const visible = filter === 'ALL' ? appointments : appointments.filter((a) => a.status === filter);
  const next = upNext(appointments);
  const busiest = Math.max(1, ...stats.byDoctor.map((d) => d.appointments));

  return (
    <>
      <section className="kpis">
        <Kpi tone="teal" label="Appointments" value={stats.total} hint={`${stats.scheduled} still to come`} />
        <Kpi tone="amber" label="In waiting room" value={stats.checkedIn} hint="Checked in, not yet seen" />
        <Kpi tone="green" label="Completed" value={stats.completed} hint="Consultations finished" />
        <Kpi tone="rose" label="Cancelled / no-show" value={stats.cancelled + stats.noShow} hint={`${stats.noShow} no-show`} />
      </section>

      <section className="grid">
        <div className="panel">
          <div className="panel-head">
            <div>
              <h2>Schedule</h2>
              <p className="muted">Check patients in as they arrive and close the visit when done.</p>
            </div>
            <div className="chips" role="tablist">
              {['ALL', ...STATUSES].map((s) => (
                <button key={s} className={filter === s ? 'chip selected' : 'chip'} onClick={() => setFilter(s)}>
                  {s === 'ALL' ? 'All' : STATUS_LABELS[s]}
                </button>
              ))}
            </div>
          </div>

          {loading ? <Empty>Loading schedule…</Empty> : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Time</th><th>Patient · reason</th><th>Doctor</th><th>Status</th><th aria-label="Actions" /></tr>
                </thead>
                <tbody>
                  {visible.map((a) => (
                    <tr key={a.id}>
                      <td className="time"><b>{formatTime(a.scheduled_at)}</b><small>– {endTime(a.scheduled_at, a.duration_minutes)}</small></td>
                      <td><div className="who"><Avatar name={a.patient.full_name} /><div><b>{a.patient.full_name}</b><small className="reason">{a.reason}</small></div></div></td>
                      <td><b>{a.doctor.full_name}</b><small>{a.doctor.specialty}</small></td>
                      <td><StatusBadge status={a.status} /></td>
                      <td className="actions">
                        <div>
                          {nextActions(a.status).map((action) => (
                            <button key={action.status} className={`btn-${action.tone}`} onClick={() => onStatus(a, action.status)}>{action.label}</button>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!visible.length && <Empty>No appointments {filter === 'ALL' ? 'on this day' : 'with this status'}.</Empty>}
            </div>
          )}
        </div>

        <aside className="side-panels">
          <div className="panel up-next">
            <p className="eyebrow">UP NEXT</p>
            {next ? (
              <>
                <h3>{formatTime(next.scheduled_at)} · {next.patient.full_name}</h3>
                <p className="muted">{next.reason} — {next.doctor.full_name}</p>
                <button className="btn-primary" onClick={() => onStatus(next, 'CHECKED_IN')}>Check in now</button>
              </>
            ) : <p className="muted">No upcoming visits for the rest of the day.</p>}
          </div>

          <div className="panel">
            <div className="panel-head"><div><h2>Doctor load</h2><p className="muted">Active appointments per doctor.</p></div></div>
            {stats.byDoctor.length ? stats.byDoctor.map((d) => (
              <div className="load" key={d.doctor_id}>
                <div className="load-label"><b>{d.full_name}</b><small>{d.specialty}</small></div>
                <div className="bar"><i style={{ width: `${(d.appointments / busiest) * 100}%` }} /></div>
                <span className="load-count">{d.appointments}</span>
              </div>
            )) : <Empty>No bookings yet.</Empty>}
          </div>
        </aside>
      </section>
    </>
  );
}
