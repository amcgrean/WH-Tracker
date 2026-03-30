import os
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, jsonify, send_from_directory, abort
from werkzeug.utils import secure_filename

from app.extensions import db
from app.Models.models import CreditImage
from app.Routes.main import main_bp
from app.Routes.main.helpers import ALLOWED_UPLOAD_EXTENSIONS, credit_upload_dir


@main_bp.route('/credits/')
@main_bp.route('/credits')
def credits_search():
    """Search / landing page for RMA credit images."""
    rma = request.args.get('rma', '').strip()
    images = []
    if rma:
        images = CreditImage.query.filter_by(rma_number=rma).order_by(CreditImage.received_at.desc()).all()
    return render_template('credits/search.html', rma=rma, images=images)


@main_bp.route('/credits/<rma_number>')
def credits_detail(rma_number):
    """Detail page: shows all images for a given RMA number."""
    images = CreditImage.query.filter_by(rma_number=rma_number).order_by(CreditImage.received_at.desc()).all()
    return render_template('credits/detail.html', rma_number=rma_number, images=images)


@main_bp.route('/credits/image/<int:image_id>')
def credits_serve_image(image_id):
    """Serve an image file from the uploads folder."""
    img = CreditImage.query.get_or_404(image_id)
    upload_dir = credit_upload_dir()
    rma_dir = os.path.join(upload_dir, img.rma_number)
    if not os.path.exists(os.path.join(rma_dir, img.filename)):
        abort(404)
    return send_from_directory(rma_dir, img.filename)


@main_bp.route('/credits/<rma_number>/upload', methods=['POST'])
def credits_manual_upload(rma_number):
    """Manual drag-and-drop upload from the dispatcher's browser."""
    files = request.files.getlist('images')
    if not files:
        flash('No files selected.', 'warning')
        return redirect(url_for('main.credits_detail', rma_number=rma_number))

    upload_dir = credit_upload_dir()
    rma_dir = os.path.join(upload_dir, rma_number)
    os.makedirs(rma_dir, exist_ok=True)

    saved = 0
    for f in files:
        if not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_UPLOAD_EXTENSIONS:
            flash(f'Skipped {f.filename} — unsupported file type.', 'warning')
            continue

        timestamp_prefix = datetime.utcnow().strftime('%Y%m%d_%H%M%S_')
        safe_name = timestamp_prefix + secure_filename(f.filename)
        file_path = os.path.join(rma_dir, safe_name)
        f.save(file_path)

        img = CreditImage(
            rma_number    = rma_number,
            filename      = safe_name,
            filepath      = os.path.join(rma_number, safe_name),
            email_from    = 'manual-upload',
            email_subject = f'Manually uploaded by dispatcher',
            received_at   = datetime.utcnow(),
        )
        db.session.add(img)
        saved += 1

    db.session.commit()
    flash(f'{saved} image(s) uploaded successfully.', 'success')
    return redirect(url_for('main.credits_detail', rma_number=rma_number))


@main_bp.route('/api/credits/<rma_number>/images')
def api_credits_images(rma_number):
    """JSON list of images for a given RMA — used for dynamic refresh."""
    images = CreditImage.query.filter_by(rma_number=rma_number).order_by(CreditImage.received_at.desc()).all()
    return jsonify([{
        'id':            img.id,
        'filename':      img.filename,
        'url':           url_for('main.credits_serve_image', image_id=img.id),
        'email_from':    img.email_from,
        'email_subject': img.email_subject,
        'received_at':   img.received_at.strftime('%Y-%m-%d %I:%M %p') if img.received_at else None,
        'uploaded_at':   img.uploaded_at.strftime('%Y-%m-%d %I:%M %p') if img.uploaded_at else None,
    } for img in images])
