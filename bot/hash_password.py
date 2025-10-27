import bcrypt
import sys

def hash_password(password: str) -> str:
    """Hashes a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed_password.decode('utf-8')

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python hash_password.py <password>")
        sys.exit(1)

    plain_password = sys.argv[1]
    hashed_password = hash_password(plain_password)
    print(f"Original password: {plain_password}")
    print(f"Hashed password: {hashed_password}")
