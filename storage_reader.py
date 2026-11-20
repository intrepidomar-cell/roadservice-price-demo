"""Read one historical synthetic PDF from a PRIVATE Supabase Storage bucket.

Never accept arbitrary URLs or paths from the browser. The object locator is
stored in the read-only PostgreSQL documents table and must match the demo
bucket and path. Only for synthetic demo documents until corporate access is
approved and authorization is implemented.
"""

import hashlib
import re
from urllib.parse import urlsplit

DEMO_BUCKET = 'roadservice-synthetic-pdfs'
DEMO_PATH = re.compile(r'^fleetperform/FP-DEMO-\d{4}\.pdf$')
MAX_PDF_BYTES = 15 * 1024 * 1024


class StorageDocumentError(Exception):
    """An expected storage or file-integrity error (no secret content)."""


def parse_storage_locator(locator: str):
    """Return an allowed (bucket, object_path); reject traversal and foreign URLs."""
    if not isinstance(locator, str):
        raise StorageDocumentError('The historical document has no Storage locator.')
    prefix = f'storage://{DEMO_BUCKET}/'
    if not locator.startswith(prefix):
        raise StorageDocumentError('The PDF locator does not belong to the permitted demo bucket.')
    path = locator[len(prefix):]
    if not DEMO_PATH.fullmatch(path):
        raise StorageDocumentError('The PDF locator is not a permitted FleetPerform demo path.')
    return DEMO_BUCKET, path


def validate_project_url(url: str):
    """Restrict network destination to the configured Supabase project endpoint."""
    parts = urlsplit(url)
    if (parts.scheme != 'https' or not parts.hostname or
            not parts.hostname.endswith('.supabase.co') or
            parts.hostname == 'supabase.co' or
            parts.username or parts.password or parts.port or
            parts.path not in ('', '/') or parts.query or parts.fragment):
        raise StorageDocumentError('Invalid Supabase project URL in server Secrets.')
    return url.rstrip('/')


def verify_pdf_hash(data: bytes, expected_sha256: str):
    """Return (matched, note), where None means no expected hash is available."""
    if not expected_sha256:
        return None, 'No SHA-256 is stored for this PDF.'
    if not re.fullmatch(r'[0-9a-fA-F]{64}', str(expected_sha256)):
        return False, 'The SHA-256 in PostgreSQL has an invalid format.'
    matched = hashlib.sha256(data).hexdigest() == expected_sha256.lower()
    return matched, ('PDF SHA-256 matches PostgreSQL.' if matched else
                     'PDF SHA-256 does NOT match the source registered in PostgreSQL.')


def download_private_pdf(locator: str, project_url: str, secret_key: str, *, client_factory=None):
    """Download a single allowed object on the server using the official SDK.

    SUPABASE_SECRET_KEY / service role credentials must NEVER reach the browser.
    This demo assumes access to the whole app is restricted and uses synthetic
    data only; a corporate deployment needs per-user authorization and roles.
    """
    bucket, path = parse_storage_locator(locator)
    safe_url = validate_project_url(project_url)
    if not isinstance(secret_key, str) or not secret_key.strip():
        raise StorageDocumentError('SUPABASE_SECRET_KEY is missing from server Secrets.')
    if client_factory is None:
        from supabase import create_client
        client_factory = create_client
    try:
        client = client_factory(safe_url, secret_key)
        data = client.storage.from_(bucket).download(path)
    except Exception as exc:
        # Never reflect raw exception strings; some clients include request headers.
        raise StorageDocumentError(
            f'Could not access the private PDF (error type: {type(exc).__name__}).'
        ) from None
    if not isinstance(data, (bytes, bytearray)):
        raise StorageDocumentError('Storage did not return PDF bytes.')
    data = bytes(data)
    if len(data) > MAX_PDF_BYTES or not data.startswith(b'%PDF-'):
        raise StorageDocumentError('The historical file is not an allowed digital PDF or exceeds 15 MB.')
    return data
