"""Business metrics exported on /metrics next to the HTTP metrics from the instrumentator."""
from prometheus_client import Counter

APPOINTMENTS_BOOKED = Counter(
    "clinicflow_appointments_booked_total",
    "Appointments booked, by doctor specialty",
    ["specialty"],
)
APPOINTMENT_STATUS_CHANGES = Counter(
    "clinicflow_appointment_status_changes_total",
    "Appointment status transitions, by new status",
    ["status"],
)
BOOKING_CONFLICTS = Counter(
    "clinicflow_booking_conflicts_total",
    "Bookings rejected because the doctor already had an overlapping appointment",
)
