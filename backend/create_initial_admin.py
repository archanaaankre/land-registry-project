import logging
from getpass import getpass

from app import create_app, db
from app.auth.errors import InvalidInputError, ResourceConflictError
from app.auth.service import hash_password
from app.auth.validation import validate_registration_input
from app.models import Role
from app.persistence.errors import DatabaseUnavailableError
from app.persistence.repositories import SqlAlchemyUserRepository


def main():
    name = input("Admin name: ").strip()
    if not name or len(name) > 100:
        raise SystemExit("Name must be between 1 and 100 characters.")

    email = input("Admin email address: ").strip()
    password = getpass("Admin password: ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match. No account was created.")

    try:
        validated = validate_registration_input(
            {"email": email, "password": password, "role": Role.ADMIN.value}
        )
    except InvalidInputError as error:
        raise SystemExit(error.message) from None

    app = create_app()
    with app.app_context():
        repository = SqlAlchemyUserRepository()
        try:
            user = repository.create_initial_admin(
                name=name,
                email=validated["email"],
                password_hash=hash_password(validated["password"]),
            )
        except ResourceConflictError as error:
            db.session.rollback()
            raise SystemExit(error.message) from None
        except (DatabaseUnavailableError, InvalidInputError) as error:
            db.session.rollback()
            message = (
                "The database is temporarily unavailable. No account was created."
                if isinstance(error, DatabaseUnavailableError)
                else error.message
            )
            raise SystemExit(message) from None

    print("Initial Admin account created successfully.")
    print("User ID:", user.id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR, format="%(levelname)s: %(message)s")
    main()
