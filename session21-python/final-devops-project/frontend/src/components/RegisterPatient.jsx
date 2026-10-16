import { useState } from 'react';
import { api } from '../api.js';
import { Modal } from './ui.jsx';

export default function RegisterPatient({ onClose, onRegistered }) {
  const [error, setError] = useState('');

  const submit = async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError('');
    try {
      await api.registerPatient({
        full_name: form.get('full_name'),
        phone: form.get('phone'),
        email: form.get('email') || null,
        date_of_birth: form.get('date_of_birth') || null,
      });
      onRegistered();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <Modal eyebrow="NEW PATIENT" title="Register a patient" onClose={onClose}>
      <form onSubmit={submit} className="form">
        <label>Full name<input name="full_name" required minLength={2} placeholder="e.g. Riya Sharma" /></label>
        <div className="form-row">
          <label>Phone<input name="phone" required placeholder="+91 98200 11111" /></label>
          <label>Date of birth<input type="date" name="date_of_birth" /></label>
        </div>
        <label>Email (optional)<input type="email" name="email" placeholder="riya@example.com" /></label>
        {error && <div className="alert" role="alert">⚠ {error}</div>}
        <button className="primary full">Register patient</button>
      </form>
    </Modal>
  );
}
