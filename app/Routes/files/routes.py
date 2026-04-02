"""File management routes — upload, download, list, and soft-delete files.

All file binaries are stored in Cloudflare R2 (S3-compatible).
Metadata lives in the `files` and `file_versions` Postgres tables.
"""

import os

from flask import jsonify, request, redirect, abort, session
from werkzeug.utils import secure_filename

from app.extensions import db
from app.Models.models import File, FileVersion
from app.Routes.files import files_bp
from app.Services.storage_service import StorageService

ALLOWED_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.webp',
    '.pdf', '.tiff', '.tif',
    '.xlsx', '.xls', '.csv',
    '.doc', '.docx',
    '.heic', '.heif',
}


def _get_uploader():
    """Return current user's display name or email from session."""
    return session.get('display_name') or session.get('email') or 'unknown'


@files_bp.route('/upload', methods=['POST'])
def upload():
    """
    Upload one or more files and attach to an entity.

    Form fields:
        entity_type (str): e.g. 'rma', 'bid', 'takeoff', 'job'
        entity_id   (str): e.g. RMA number, bid ID
        category    (str, optional): e.g. 'plan', 'quote', 'photo'
        files       (file[]): one or more files
    """
    entity_type = request.form.get('entity_type', '').strip()
    entity_id = request.form.get('entity_id', '').strip()
    category = request.form.get('category', '').strip() or None

    if not entity_type or not entity_id:
        return jsonify({'error': 'entity_type and entity_id are required'}), 400

    uploaded_files = request.files.getlist('files')
    if not uploaded_files:
        return jsonify({'error': 'No files provided'}), 400

    storage = StorageService()
    if not storage.is_available:
        return jsonify({'error': 'File storage is not configured (R2 credentials missing)'}), 503

    results = []
    for f in uploaded_files:
        if not f.filename:
            continue

        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            results.append({'filename': f.filename, 'error': 'unsupported file type'})
            continue

        safe_name = secure_filename(f.filename)
        object_key = StorageService.build_object_key(entity_type, entity_id, safe_name)

        # Get file size by seeking to end
        f.seek(0, os.SEEK_END)
        size_bytes = f.tell()
        f.seek(0)

        storage.upload_file(f, object_key, content_type=f.content_type)

        file_record = File(
            entity_type=entity_type,
            entity_id=entity_id,
            category=category,
            original_filename=f.filename,
            object_key=object_key,
            mime_type=f.content_type,
            size_bytes=size_bytes,
            uploaded_by=_get_uploader(),
        )
        db.session.add(file_record)
        db.session.flush()

        # Create initial version
        version = FileVersion(
            file_id=file_record.id,
            version_number=1,
            object_key=object_key,
            size_bytes=size_bytes,
            change_note='Initial upload',
            created_by=_get_uploader(),
        )
        db.session.add(version)

        results.append({
            'id': file_record.id,
            'filename': f.filename,
            'object_key': object_key,
            'size_bytes': size_bytes,
        })

    db.session.commit()
    return jsonify({'uploaded': results}), 201


@files_bp.route('/<int:file_id>')
def download(file_id):
    """Redirect to a presigned R2 URL for the file."""
    file_record = File.query.get_or_404(file_id)
    if file_record.is_deleted:
        abort(404)

    storage = StorageService()
    url = storage.generate_presigned_url(file_record.object_key)
    return redirect(url)


@files_bp.route('/<int:file_id>/info')
def info(file_id):
    """Return JSON metadata for a file."""
    file_record = File.query.get_or_404(file_id)
    if file_record.is_deleted:
        abort(404)

    versions = FileVersion.query.filter_by(file_id=file_id).order_by(
        FileVersion.version_number.desc()
    ).all()

    return jsonify({
        'id': file_record.id,
        'entity_type': file_record.entity_type,
        'entity_id': file_record.entity_id,
        'category': file_record.category,
        'original_filename': file_record.original_filename,
        'mime_type': file_record.mime_type,
        'size_bytes': file_record.size_bytes,
        'uploaded_by': file_record.uploaded_by,
        'created_at': file_record.created_at.isoformat() if file_record.created_at else None,
        'versions': [{
            'version_number': v.version_number,
            'size_bytes': v.size_bytes,
            'change_note': v.change_note,
            'created_at': v.created_at.isoformat() if v.created_at else None,
            'created_by': v.created_by,
        } for v in versions],
    })


@files_bp.route('/<int:file_id>', methods=['DELETE'])
def delete(file_id):
    """Soft-delete a file (set is_deleted=True). Does not remove from R2."""
    file_record = File.query.get_or_404(file_id)
    file_record.is_deleted = True
    db.session.commit()
    return jsonify({'status': 'deleted', 'id': file_id})


@files_bp.route('/entity/<entity_type>/<entity_id>')
def list_for_entity(entity_type, entity_id):
    """List all active files for a given entity."""
    records = File.query.filter_by(
        entity_type=entity_type,
        entity_id=entity_id,
        is_deleted=False,
    ).order_by(File.created_at.desc()).all()

    storage = StorageService() if records and StorageService().is_available else None

    return jsonify([{
        'id': f.id,
        'category': f.category,
        'original_filename': f.original_filename,
        'mime_type': f.mime_type,
        'size_bytes': f.size_bytes,
        'uploaded_by': f.uploaded_by,
        'created_at': f.created_at.isoformat() if f.created_at else None,
        'download_url': f'/files/{f.id}',
    } for f in records])
