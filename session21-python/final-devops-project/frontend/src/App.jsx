import { useCallback, useEffect, useState } from 'react';
import { api } from './api.js';
import { isoDate } from './lib/schedule.js';
import BookAppointment from './components/BookAppointment.jsx';
import RegisterPatient from './components/RegisterPatient.jsx';
import Today from './views/Today.jsx';
import Patients from './views/Patients.jsx';
import Doctors from './views/Doctors.jsx';

const EMPTY_STATS = { total: 0, scheduled: 0, checkedIn: 0, completed: 0, cancelled: 0, noShow: 0, patients: 0, activeDoctors: 0, byDoctor: [] };
const VIEWS = [
  { id: 'today', icon: '◷', label: 'Schedule' },
  { id: 'patients', icon: '☺', label: 'Patients' },
  { id: 'doctors', icon: '✚', label: 'Doctors' },
];

export default function App() {
  const [view, setView] = useState('today');
  const [day, setDay] = useState(isoDate());
  const [stats, setStats] = useState(EMPTY_STATS);
  const [appointments, setAppointments] = useState([]);
  const [patients, setPatients] = useState([]);
  const [doctors, setDoctors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [modal, setModal] = useState(null);
  const [version, setVersion] = useState(0); // bump to make child views refetch

  const load = useCallback(async () => {
    try {
      setError('');
      const [s, a, p, d] = await Promise.all([api.stats(day), api.appointments(day), api.patients(), api.doctors()]);
      setStats(s);
      setAppointments(a);
      setPatients(p);
      setDoctors(d);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [day]);

  useEffect(() => { load(); }, [load, version]);
  const refresh = () => setVersion((v) => v + 1);

  const changeStatus = async (appointment, status) => {
    try {
      await api.updateAppointment(appointment.id, { status });
      refresh();
    } catch (e) {
      setError(e.message);
    }
  };

  const shiftDay = (delta) => {
    const d = new Date(`${day}T00:00:00`);
    d.setDate(d.getDate() + delta);
    setDay(isoDate(d));
  };

  const title = VIEWS.find((v) => v.id === view).label;
  const prettyDay = new Date(`${day}T00:00:00`).toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' });

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">✚</span>
          <div><b>ClinicFlow</b><small>Front desk</small></div>
        </div>
        <nav>
          {VIEWS.map((v) => (
            <button key={v.id} className={view === v.id ? 'active' : ''} onClick={() => setView(v.id)}>
              <span aria-hidden="true">{v.icon}</span> <span>{v.label}</span>
            </button>
          ))}
        </nav>
        <div className="side-bottom">
          <div className="clinic-card">
            <strong>Open 08:00 – 20:00</strong>
            <p>{stats.activeDoctors} doctors available · {stats.patients} patients on file</p>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <p className="eyebrow">CLINICFLOW / {title.toUpperCase()}</p>
            <h1>{view === 'today' ? prettyDay : title}</h1>
          </div>
          <div className="toolbar">
            {view === 'today' && (
              <div className="day-picker">
                <button onClick={() => shiftDay(-1)} aria-label="Previous day">‹</button>
                <input type="date" value={day} onChange={(e) => e.target.value && setDay(e.target.value)} aria-label="Day" />
                <button onClick={() => shiftDay(1)} aria-label="Next day">›</button>
              </div>
            )}
            <button className="btn-ghost" onClick={() => setModal('patient')}>＋ Patient</button>
            <button className="btn-primary" onClick={() => setModal('book')}>＋ Book appointment</button>
          </div>
        </header>

        {error && <div className="alert" role="alert">⚠ {error}. Is the API running? Refresh to retry.</div>}

        {view === 'today' && <Today stats={stats} appointments={appointments} loading={loading} onStatus={changeStatus} />}
        {view === 'patients' && <Patients version={version} onRegister={() => setModal('patient')} onChanged={refresh} />}
        {view === 'doctors' && <Doctors doctors={doctors} stats={stats} onChanged={refresh} />}
      </main>

      {modal === 'book' && (
        <BookAppointment day={day} patients={patients} doctors={doctors} onClose={() => setModal(null)} onBooked={() => { setModal(null); refresh(); }} />
      )}
      {modal === 'patient' && (
        <RegisterPatient onClose={() => setModal(null)} onRegistered={() => { setModal(null); refresh(); }} />
      )}
    </div>
  );
}
