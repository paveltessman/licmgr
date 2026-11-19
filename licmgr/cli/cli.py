import base64
from pathlib import Path

import click
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from licmgr.exceptions import LicmgrException
from licmgr.services.license.service import LicenseService
from licmgr.storage import DEFAULT_DB_PATH
from licmgr.storage import LicenseRepo
from licmgr.storage import open_database


@click.group()
def cli() -> None:
    """Manage licenses."""


@cli.command("keypair")
def generate_keypair() -> None:
    """Generate an X25519 key pair for activation request encryption."""
    try:

        private_key = X25519PrivateKey.generate()
        private_bytes = private_key.private_bytes_raw()
        public_bytes = private_key.public_key().public_bytes_raw()

    except UnsupportedAlgorithm as error:

        raise click.ClickException("X25519 key generation is unavailable") from error

    private_value = base64.b64encode(private_bytes).decode("ascii")
    public_value = base64.b64encode(public_bytes).decode("ascii")
    click.echo(f"LICMGR_SERVER_PRIVATE_KEY={private_value}")
    click.echo(f"LICMGR_SERVER_PUBLIC_KEY={public_value}")


@cli.group()
def keys() -> None:
    """Manage license keys."""


@keys.command("create")
@click.option(
    "--max-devices",
    type=click.IntRange(1, 2**63 - 1),
    default=1,
    show_default=True,
    help="Maximum number of devices that can activate the key.",
)
@click.option(
    "--db",
    "db_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DEFAULT_DB_PATH,
    show_default=True,
    help="Path to the SQLite database.",
)
def create_key(max_devices: int, db_path: Path) -> None:
    """Issue a new license key."""
    try:
        with open_database(db_path) as database:
            key = LicenseService(LicenseRepo(database)).create_license(max_devices)
    except LicmgrException as error:
        raise click.ClickException(str(error)) from error

    click.echo(key)
