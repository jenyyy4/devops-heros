import { api } from '../api.js';
import { Avatar } from '../components/ui.jsx';

export default function Doctors({ doctors, stats, onChanged }) {
  const today = Object.fromEntries(stats.byDoctor.map((d) => [d.doctor_id, d.appointments]));

  const toggle = async (doctor) => {
    await api.updateDoctor(doctor.id, { active: !doctor.active });
    onChanged();
  };

  return (
    <section className="doctor-grid">
      {doctors.map((d) => (
        <article key={d.id} className={`panel doctor ${d.active ? '' : 'inactive'}`}>
          <div className="who">
            <Avatar name={d.full_name} tone="blue" />
            <div><b>{d.full_name}</b><small>{d.specialty}</small></div>
          </div>
          <dl>
            <div><dt>Room</dt><dd>{d.room || '—'}</dd></div>
            <div><dt>Today</dt><dd>{today[d.id] ?? 0} appt{(today[d.id] ?? 0) === 1 ? '' : 's'}</dd></div>
            <div><dt>Status</dt><dd>{d.active ? 'Available' : 'On leave'}</dd></div>
          </dl>
          <button className={d.active ? 'btn-ghost' : 'btn-primary'} onClick={() => toggle(d)}>
            {d.active ? 'Mark on leave' : 'Mark available'}
          </button>
        </article>
      ))}
    </section>
  );
}
