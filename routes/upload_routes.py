"""
routes/upload_routes.py - Multi-file upload management for customers.
"""
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, current_app)
from flask_login import login_required, current_user
from extensions import db
from models.upload import Upload
from models.customer import Customer
from utils.helpers import log_activity
from utils.file_handler import save_upload, delete_file

upload_bp = Blueprint('uploads', __name__, url_prefix='/uploads')

UPLOAD_TYPES = ['Installation', 'Service', 'Payment Proof', 'KYC', 'Other']


@upload_bp.route('/customer/<int:cust_id>', methods=['GET', 'POST'])
@login_required
def upload_for_customer(cust_id):
    """Upload files for a specific customer."""
    if not current_user.has_permission('uploads'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))

    customer = db.get_or_404(Customer, cust_id)

    if request.method == 'POST':
        files = request.files.getlist('files')
        upload_type = request.form.get('upload_type', 'Other')
        remarks = request.form.get('remarks', '').strip()

        if not files or all(f.filename == '' for f in files):
            flash('No files selected.', 'warning')
            return redirect(request.url)

        max_files = current_app.config.get('MAX_FILES_PER_REQUEST', 10)
        if len(files) > max_files:
            flash(f'Maximum {max_files} files allowed per upload.', 'danger')
            return redirect(request.url)

        success_count = 0
        errors = []

        subfolder_map = {
            'Installation': f'customers/CUST_{cust_id}/installation',
            'Service': f'customers/CUST_{cust_id}/service',
            'Payment Proof': f'customers/CUST_{cust_id}/payment_proof',
            'KYC': f'customers/CUST_{cust_id}/kyc',
            'Other': f'customers/CUST_{cust_id}/other',
        }
        subfolder = subfolder_map.get(upload_type, f'customers/CUST_{cust_id}/other')

        for file in files:
            if not file.filename:
                continue
            try:
                rel_path = save_upload(file, subfolder)
                upload_record = Upload(
                    customer_id=cust_id,
                    upload_type=upload_type,
                    file_path=rel_path,
                    file_name=file.filename,
                    file_size=file.content_length,
                    remarks=remarks,
                    uploaded_by=current_user.username,
                )
                db.session.add(upload_record)
                success_count += 1
            except ValueError as ve:
                errors.append(f'{file.filename}: {ve}')
            except Exception as exc:
                current_app.logger.error(f'Upload error: {exc}', exc_info=True)
                errors.append(f'{file.filename}: Server error')

        if success_count > 0:
            db.session.commit()
            log_activity(current_user.username, 'Upload', 'Customer', cust_id,
                         f'Uploaded {success_count} files ({upload_type})', request.remote_addr)
            flash(f'{success_count} file(s) uploaded successfully!', 'success')

        for err in errors:
            flash(err, 'warning')

        return redirect(url_for('customers.view', cust_id=cust_id))

    uploads = Upload.query.filter_by(customer_id=cust_id).order_by(Upload.uploaded_at.desc()).all()
    return render_template(
        'uploads/customer_uploads.html',
        customer=customer,
        uploads=uploads,
        upload_types=UPLOAD_TYPES,
        active_page='uploads',
    )


@upload_bp.route('/delete/<int:upload_id>', methods=['POST'])
@login_required
def delete_upload(upload_id):
    """Delete an uploaded file."""
    if not current_user.is_admin():
        flash('Only admins can delete uploads.', 'danger')
        return redirect(url_for('dashboard.index'))

    upload = db.get_or_404(Upload, upload_id)
    cust_id = upload.customer_id

    try:
        delete_file(upload.file_path)
        db.session.delete(upload)
        db.session.commit()
        log_activity(current_user.username, 'Delete', 'Upload', upload_id,
                     f'Deleted upload {upload.file_name}', request.remote_addr)
        flash('File deleted.', 'success')
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(f'Error deleting upload {upload_id}: {exc}', exc_info=True)
        flash(f'Error deleting file: {exc}', 'danger')

    return redirect(url_for('customers.view', cust_id=cust_id) if cust_id else url_for('dashboard.index'))
