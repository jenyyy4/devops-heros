// Pure helpers shared by the UI and covered by `npm test` (node --test).

export const STATUSES = ['SCHEDULED', 'CHECKED_IN', 'COMPLETED', 'CANCELLED', 'NO_SHOW'];

export const STATUS_LABELS = {
  SCHEDULED: 'Scheduled',
  CHECKED_IN: 'Checked in',
  COMPLETED: 'Completed',
  CANCELLED: 'Cancelled',
  NO_SHOW: 'No-show',
};

// Mirrors the backend's TRANSITIONS table: the buttons offered for each status.
const ACTIONS = {
  SCHEDULED: [
    { status: 'CHECKED_IN', label: 'Check in', tone: 'primary' },
    { status: 'NO_SHOW', label: 'No-show', tone: 'ghost' },
    { status: 'CANCELLED', label: 'Cancel', tone: 'danger' },
  ],
  CHECKED_IN: [
    { status: 'COMPLETED', label: 'Complete', tone: 'primary' },
    { status: 'CANCELLED', label: 'Cancel', tone: 'danger' },
  ],
};

export function nextActions(status) {
  return ACTIONS[status] ?? [];
}

// Local calendar date as YYYY-MM-DD (toISOString() would shift to UTC).
export function isoDate(date = new Date()) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

// "2030-01-15T09:05:00" -> "09:05" (times are clinic-local wall-clock, no timezone).
export function formatTime(isoDateTime) {
  return isoDateTime.slice(11, 16);
}

export function endTime(isoDateTime, durationMinutes) {
  const [h, m] = formatTime(isoDateTime).split(':').map(Number);
  const total = h * 60 + m + durationMinutes;
  return `${String(Math.floor(total / 60) % 24).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
}

export function initials(fullName) {
  return fullName
    .replace(/^Dr\.?\s+/i, '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join('');
}

export function ageFrom(dateOfBirth, today = new Date()) {
  if (!dateOfBirth) return null;
  const dob = new Date(`${dateOfBirth}T00:00:00`);
  let age = today.getFullYear() - dob.getFullYear();
  const beforeBirthday = today.getMonth() < dob.getMonth() || (today.getMonth() === dob.getMonth() && today.getDate() < dob.getDate());
  if (beforeBirthday) age -= 1;
  return age;
}

// The next appointment that has not been seen yet (for the "Up next" card).
export function upNext(appointments, now = new Date()) {
  const clock = `${isoDate(now)}T${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
  return appointments.find((a) => a.status === 'SCHEDULED' && a.scheduled_at.slice(0, 16) >= clock) ?? null;
}
