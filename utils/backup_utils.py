"""
utils/backup_utils.py - SQLite database backup and restore utilities.
"""
import os
import glob
import shutil
from datetime import datetime
from flask import current_app


def create_backup() -> str:
    """
    Copy the current SQLite database to the backups/ folder.
    Returns the backup file path.
    """
    backup_dir = current_app.config['BACKUP_FOLDER']
    os.makedirs(backup_dir, exist_ok=True)

    db_uri = current_app.config['SQLALCHEMY_DATABASE_URI']
    # Extract file path from SQLite URI: sqlite:////absolute/path
    db_path = db_uri.replace('sqlite:///', '').replace('sqlite:////', '/')

    if not os.path.exists(db_path):
        raise FileNotFoundError(f'Database not found at: {db_path}')

    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    backup_name = f'homzho_backup_{timestamp}.db'
    backup_path = os.path.join(backup_dir, backup_name)

    shutil.copy2(db_path, backup_path)

    # Retain only the latest 30 backups
    _prune_old_backups(backup_dir, keep=30)

    return backup_path


def _prune_old_backups(backup_dir: str, keep: int = 30):
    """Delete oldest backups keeping only the latest `keep` files."""
    pattern = os.path.join(backup_dir, 'homzho_backup_*.db')
    files = sorted(glob.glob(pattern))
    if len(files) > keep:
        for old_file in files[:-keep]:
            try:
                os.remove(old_file)
            except OSError:
                pass


def list_backups() -> list:
    """Return list of backup file info dicts sorted newest first."""
    backup_dir = current_app.config['BACKUP_FOLDER']
    os.makedirs(backup_dir, exist_ok=True)
    pattern = os.path.join(backup_dir, 'homzho_backup_*.db')
    files = sorted(glob.glob(pattern), reverse=True)
    result = []
    for f in files:
        stat = os.stat(f)
        result.append({
            'filename': os.path.basename(f),
            'path': f,
            'size_mb': round(stat.st_size / (1024 * 1024), 2),
            'created': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
        })
    return result


def restore_backup(backup_path: str):
    """
    Replace the current database with a backup.
    WARNING: Destructive operation — always create a backup before calling this.
    """
    db_uri = current_app.config['SQLALCHEMY_DATABASE_URI']
    db_path = db_uri.replace('sqlite:///', '').replace('sqlite:////', '/')

    if not os.path.exists(backup_path):
        raise FileNotFoundError(f'Backup file not found: {backup_path}')

    # Safety: backup current DB before overwriting
    if os.path.exists(db_path):
        ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        pre_restore_backup = db_path + f'.pre_restore_{ts}'
        shutil.copy2(db_path, pre_restore_backup)

    shutil.copy2(backup_path, db_path)
