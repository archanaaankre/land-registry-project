import sys
from getpass import getpass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import create_app
from app.auth.service import hash_password
from app.models import Role
from app.persistence.repositories import SqlAlchemyUserRepository

app = create_app()

with app.app_context():
    email = input("Test Registrar email: ").strip().lower()
    password = getpass("Test Registrar password: ")
    confirm = getpass("Confirm password: ")

    if not email or password != confirm:
        raise SystemExit("Email is required and passwords must match.")

    repo = SqlAlchemyUserRepository()

    if repo.get_user_by_email(email) is not None:
        raise SystemExit("That email already exists. No account was created.")

    user = repo.create_user(
        name="Test Registrar",
        email=email,
        password_hash=hash_password(password),
        role=Role.REGISTRAR,
    )

    print("\nRegistrar test account created successfully.")
    print("User ID:", user.id)
    print("Role:", user.role.value)
