import test from 'node:test';
import assert from 'node:assert/strict';
import { ageFrom, endTime, formatTime, initials, isoDate, nextActions, upNext } from './schedule.js';

test('nextActions follows the appointment workflow', () => {
  assert.deepEqual(nextActions('SCHEDULED').map((a) => a.status), ['CHECKED_IN', 'NO_SHOW', 'CANCELLED']);
  assert.deepEqual(nextActions('CHECKED_IN').map((a) => a.status), ['COMPLETED', 'CANCELLED']);
  assert.deepEqual(nextActions('COMPLETED'), []);
  assert.deepEqual(nextActions('CANCELLED'), []);
});

test('time helpers work on clinic-local wall-clock strings', () => {
  assert.equal(formatTime('2030-01-15T09:05:00'), '09:05');
  assert.equal(endTime('2030-01-15T09:45:00', 30), '10:15');
  assert.equal(isoDate(new Date(2030, 0, 5)), '2030-01-05');
});

test('initials skip the Dr. title', () => {
  assert.equal(initials('Dr. Meera Iyer'), 'MI');
  assert.equal(initials('Riya Sharma'), 'RS');
});

test('ageFrom handles birthdays not yet reached this year', () => {
  const today = new Date(2030, 5, 15);
  assert.equal(ageFrom('2000-06-15', today), 30);
  assert.equal(ageFrom('2000-06-16', today), 29);
  assert.equal(ageFrom(null, today), null);
});

test('upNext returns the first scheduled appointment that is still ahead', () => {
  const list = [
    { id: 1, status: 'COMPLETED', scheduled_at: '2030-01-15T09:00:00' },
    { id: 2, status: 'SCHEDULED', scheduled_at: '2030-01-15T09:30:00' },
    { id: 3, status: 'SCHEDULED', scheduled_at: '2030-01-15T11:00:00' },
  ];
  assert.equal(upNext(list, new Date(2030, 0, 15, 10, 0)).id, 3);
  assert.equal(upNext(list, new Date(2030, 0, 15, 12, 0)), null);
});
