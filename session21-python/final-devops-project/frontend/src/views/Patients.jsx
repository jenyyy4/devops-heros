import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { ageFrom } from '../lib/schedule.js';
import { Avatar, Empty } from '../components/ui.jsx';

export default function Patients({ version, onRegister, onChanged }) {
  const [search, setSearch] = useState('');
  const [patients, setPatients] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    const timer = setTimeout(() => {
      api.patients(search).then(setPatients).catch((e) => setError(e.message));
    }, 200);
    return () => clearTimeout(timer);
  }, [search, version]);

  const remove = async (patient) => {
    setError('');
    try {
      await api.deletePatient(patient.id);
      onChanged();
    } catch (e) {
      setError(`${patient.full_name}: ${e.message}`);
    }
  };

  return (
    <div className="panel">
      <div className="panel-head">
        <div><h2>Patients</h2><p className="muted">{patients.length} registered</p></div>
        <div className="toolbar">
          <input className="search" type="search" placeholder="Search name or phone…" value={search} onChange={(e) => setSearch(e.target.value)} />
          <button className="btn-primary" onClick={onRegister}>＋ Register</button>
        </div>
      </div>
      {error && <div className="alert" role="alert">⚠ {error}</div>}
      <div className="table-wrap">
        <table>
          <thead><tr><th>Patient</th><th>Phone</th><th>Email</th><th>Age</th><th aria-label="Actions" /></tr></thead>
          <tbody>
            {patients.map((p) => (
              <tr key={p.id}>
                <td><div className="who"><Avatar name={p.full_name} tone="violet" /><div><b>{p.full_name}</b><small>#{String(p.id).padStart(4, '0')}</small></div></div></td>
                <td>{p.phone}</td>
                <td>{p.email || '—'}</td>
                <td>{ageFrom(p.date_of_birth) ?? '—'}</td>
                <td className="actions"><button className="btn-ghost" onClick={() => remove(p)} title="Only patients without appointments can be removed">Remove</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        {!patients.length && <Empty>No patients match “{search}”.</Empty>}
      </div>
    </div>
  );
}
