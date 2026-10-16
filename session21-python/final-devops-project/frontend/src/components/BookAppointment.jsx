import { useState } from 'react';
import { api } from '../api.js';
import { Modal } from './ui.jsx';

export default function BookAppointment({ day, patients, doctors, onClose, onBooked }) {
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const activeDoctors = doctors.filter((d) => d.active);

  const submit = async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSaving(true);
    setError('');
    try {
      await api.book({
        patient_id: Number(form.get('patient_id')),
        doctor_id: Number(form.get('doctor_id')),
        scheduled_at: `${form.get('date')}T${form.get('time')}:00`,
        duration_minutes: Number(form.get('duration')),
        reason: form.get('reason'),
      });
      onBooked();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal eyebrow="NEW APPOINTMENT" title="Book an appointment" onClose={onClose}>
      {!patients.length ? (
        <p className="muted">Register a patient first, then book their visit.</p>
      ) : (
        <form onSubmit={submit} className="form">
          <label>Patient
            <select name="patient_id" required>
              {patients.map((p) => <option key={p.id} value={p.id}>{p.full_name} · {p.phone}</option>)}
            </select>
          </label>
          <label>Doctor
            <select name="doctor_id" required>
              {activeDoctors.map((d) => <option key={d.id} value={d.id}>{d.full_name} — {d.specialty}</option>)}
            </select>
          </label>
          <div className="form-row">
            <label>Date<input type="date" name="date" defaultValue={day} required /></label>
            <label>Time<input type="time" name="time" defaultValue="10:00" step="300" min="08:00" max="19:50" required /></label>
            <label>Duration
              <select name="duration" defaultValue="30">
                {[15, 20, 30, 45, 60].map((m) => <option key={m} value={m}>{m} min</option>)}
              </select>
            </label>
          </div>
          <label>Reason for visit<input name="reason" required minLength={2} placeholder="e.g. Follow-up for blood pressure" /></label>
          {error && <div className="alert" role="alert">⚠ {error}</div>}
          <button className="primary full" disabled={saving}>{saving ? 'Booking…' : 'Book appointment'}</button>
        </form>
      )}
    </Modal>
  );
}
