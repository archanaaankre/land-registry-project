import os
import secrets


os.environ["JWT_SECRET_KEY"] = secrets.token_hex(32)
