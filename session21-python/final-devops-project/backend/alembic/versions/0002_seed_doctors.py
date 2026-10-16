"""seed the clinic's doctors (reference data)

Revision ID: 0002_seed_doctors
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_seed_doctors"
down_revision = "0001_create_clinic_tables"
branch_labels = None
depends_on = None

DOCTORS = [
    {"full_name": "Dr. Meera Iyer", "specialty": "General Medicine", "room": "101"},
    {"full_name": "Dr. Arjun Mehta", "specialty": "Cardiology", "room": "204"},
    {"full_name": "Dr. Sana Qureshi", "specialty": "Pediatrics", "room": "110"},
    {"full_name": "Dr. Rohan Kapoor", "specialty": "Orthopedics", "room": "305"},
    {"full_name": "Dr. Kavya Nair", "specialty": "Dermatology", "room": "212"},
]


def upgrade():
    doctors = sa.table(
        "doctors",
        sa.column("full_name", sa.String),
        sa.column("specialty", sa.String),
        sa.column("room", sa.String),
    )
    op.bulk_insert(doctors, DOCTORS)


def downgrade():
    names = ", ".join(f"'{d['full_name']}'" for d in DOCTORS)
    op.execute(f"DELETE FROM doctors WHERE full_name IN ({names})")  # nosec B608 - constant literals
