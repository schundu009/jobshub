"""
One-time migration to set administrator role for chundubabu@gmail.com
Run this script to update the user role.
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models import User


def update_admin_role():
    """Update chundubabu@gmail.com to administrator role."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == 'chundubabu@gmail.com').first()
        if user:
            old_role = user.role
            user.role = 'administrator'
            db.commit()
            print(f"SUCCESS: Updated user {user.email} from '{old_role}' to 'administrator'")
            return True
        else:
            print("User chundubabu@gmail.com not found in database")
            return False
    except Exception as e:
        print(f"ERROR: {e}")
        db.rollback()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    update_admin_role()
