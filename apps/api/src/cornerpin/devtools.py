"""Developer tools: throwaway databases for tests and end-to-end runs, and web push keys.
Local and CI only.

    uv run python -m cornerpin.devtools vapid-keys
"""

from sqlalchemy import URL, create_engine, text

from cornerpin.core.config import REPO_ROOT


def recreate_database(owner_url: URL) -> None:
    """Drop and create the database named in owner_url, then migrate it to head."""
    from alembic import command
    from alembic.config import Config

    name = owner_url.database
    if not name or not name.replace("_", "").isalnum():
        raise ValueError(f"refusing to recreate database {name!r}")
    admin = create_engine(owner_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
            conn.execute(text(f"CREATE DATABASE {name}"))
    finally:
        admin.dispose()

    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", owner_url.render_as_string(hide_password=False))
    command.upgrade(config, "head")


def vapid_keys() -> tuple[str, str]:
    """A new VAPID key pair for web push, as (public, private): the public key is what browsers
    get as `applicationServerKey`, the private key signs pushes. Both base64url, unpadded."""
    from base64 import urlsafe_b64encode

    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    def b64(raw: bytes) -> str:
        return urlsafe_b64encode(raw).rstrip(b"=").decode()

    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return b64(public), b64(key.private_numbers().private_value.to_bytes(32, "big"))


def main(argv: list[str]) -> None:
    if argv[1:] == ["vapid-keys"]:
        public, private = vapid_keys()
        print("# Web push keys for .env (local only; generate new ones for the cloud)")
        print(f"VAPID_PUBLIC_KEY={public}")
        print(f"VAPID_PRIVATE_KEY={private}")
        return
    raise SystemExit("usage: python -m cornerpin.devtools vapid-keys")


if __name__ == "__main__":
    import sys

    main(sys.argv)
