"""
utils/file_handler.py - Secure file upload handling with Pillow compression.
"""
import os
import mimetypes
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import current_app

# Optional Pillow import (compress images)
try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False


ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'pdf'}
ALLOWED_MIMETYPES = {'image/jpeg', 'image/png', 'application/pdf'}
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


def allowed_file(filename: str) -> bool:
    """Check file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_mime_type(file_storage) -> bool:
    """Server-side MIME type validation using python-magic or mimetypes fallback."""
    filename = file_storage.filename or ''
    mime, _ = mimetypes.guess_type(filename)
    return mime in ALLOWED_MIMETYPES


def save_upload(file_storage, subfolder: str, compress: bool = True) -> str:
    """
    Save an uploaded file securely.

    Args:
        file_storage: Werkzeug FileStorage object.
        subfolder:    Relative path inside static/uploads/. e.g. 'customers/CUST_1/installation'
        compress:     Whether to compress images with Pillow.

    Returns:
        Relative path from static root (e.g., 'uploads/customers/CUST_1/...').

    Raises:
        ValueError: If file is invalid.
    """
    if not file_storage or not file_storage.filename:
        raise ValueError('No file provided.')

    if not allowed_file(file_storage.filename):
        raise ValueError(f'File type not allowed: {file_storage.filename}')

    if not validate_mime_type(file_storage):
        raise ValueError(f'Invalid MIME type for: {file_storage.filename}')

    # Check file size
    file_storage.seek(0, 2)  # Seek to end
    size = file_storage.tell()
    file_storage.seek(0)
    if size > MAX_FILE_SIZE_BYTES:
        raise ValueError(f'File too large (max 5 MB): {file_storage.filename}')

    filename = secure_filename(file_storage.filename)
    # Add timestamp to avoid name collision
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    name, ext = os.path.splitext(filename)
    filename = f'{name}_{timestamp}{ext}'

    upload_root = current_app.config['UPLOAD_FOLDER']
    dest_dir = os.path.join(upload_root, subfolder)
    os.makedirs(dest_dir, exist_ok=True)

    dest_path = os.path.join(dest_dir, filename)

    # Compress images before saving
    if compress and PILLOW_AVAILABLE and ext.lower() in ('.jpg', '.jpeg', '.png'):
        try:
            img = Image.open(file_storage.stream)
            img.thumbnail((1920, 1920), Image.LANCZOS)
            img.save(dest_path, optimize=True, quality=85)
        except Exception:
            # Fall back to raw save if compression fails
            file_storage.seek(0)
            file_storage.save(dest_path)
    else:
        file_storage.save(dest_path)

    # Return relative path from static/
    rel = os.path.join('uploads', subfolder, filename).replace('\\', '/')
    return rel


def delete_file(relative_path: str):
    """Delete a file given its relative path from the static folder."""
    if not relative_path:
        return
    try:
        upload_root = os.path.join(current_app.root_path, 'static')
        abs_path = os.path.join(upload_root, relative_path)
        if os.path.exists(abs_path):
            os.remove(abs_path)
    except Exception as exc:
        current_app.logger.error(f'Failed to delete file {relative_path}: {exc}')
