from flask import (
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from app.auth import role_required
from app.extensions import db
from app.Models.models import AppUser, OTPCode, Pickster
from app.Routes.auth import auth_bp
from app.Routes.auth.helpers import AVAILABLE_ROLES


# ---------------------------------------------------------------------------
# Admin — User Management
# ---------------------------------------------------------------------------

@auth_bp.route("/users")
@role_required("admin")
def manage_users():
    users = AppUser.query.order_by(AppUser.email).all()
    picksters = Pickster.query.order_by(Pickster.name).all()
    # Build set of emails already in app_users for the import panel
    existing_emails = {u.email for u in users}
    return render_template(
        "auth/manage_users.html",
        users=users,
        picksters=picksters,
        existing_emails=existing_emails,
        available_roles=AVAILABLE_ROLES,
    )


@auth_bp.route("/users/add", methods=["GET", "POST"])
@role_required("admin")
def add_user():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        user_id = (request.form.get("user_id") or "").strip().lower()
        display_name = (request.form.get("display_name") or "").strip()
        phone = (request.form.get("phone") or "").strip() or None
        roles = request.form.getlist("roles")

        if not email:
            flash("Email is required.", "danger")
            return render_template("auth/add_edit_user.html",
                                   user=None, available_roles=AVAILABLE_ROLES)

        if AppUser.query.filter_by(email=email).first():
            flash("A user with that email already exists.", "warning")
            return render_template("auth/add_edit_user.html",
                                   user=None, available_roles=AVAILABLE_ROLES)

        user = AppUser(
            email=email,
            user_id=user_id or None,
            display_name=display_name or None,
            phone=phone,
            roles=roles,
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()
        flash(f"User {email} created.", "success")
        return redirect(url_for("auth.manage_users"))

    return render_template("auth/add_edit_user.html",
                           user=None, available_roles=AVAILABLE_ROLES)


@auth_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def edit_user(user_id):
    user = AppUser.query.get_or_404(user_id)

    if request.method == "POST":
        user.email = (request.form.get("email") or "").strip().lower() or user.email
        user.user_id = (request.form.get("user_id") or "").strip().lower() or None
        user.display_name = (request.form.get("display_name") or "").strip() or None
        user.phone = (request.form.get("phone") or "").strip() or None
        user.roles = request.form.getlist("roles")
        db.session.commit()
        flash(f"User {user.email} updated.", "success")
        return redirect(url_for("auth.manage_users"))

    return render_template("auth/add_edit_user.html",
                           user=user, available_roles=AVAILABLE_ROLES)


@auth_bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@role_required("admin")
def toggle_user(user_id):
    user = AppUser.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()
    state = "activated" if user.is_active else "deactivated"
    flash(f"User {user.email} {state}.", "success")
    return redirect(url_for("auth.manage_users"))


@auth_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@role_required("admin")
def delete_user(user_id):
    user = AppUser.query.get_or_404(user_id)
    email = user.email
    # Also clean up their OTP codes
    OTPCode.query.filter_by(email=email).delete()
    db.session.delete(user)
    db.session.commit()
    flash(f"User {email} deleted.", "success")
    return redirect(url_for("auth.manage_users"))


@auth_bp.route("/users/import-picker", methods=["POST"])
@role_required("admin")
def import_picker():
    """Create an AppUser shell from an existing Pickster record."""
    picker_id = request.form.get("picker_id")
    email = (request.form.get("email") or "").strip().lower()
    roles = request.form.getlist("roles")

    if not picker_id or not email:
        flash("Picker and email are required for import.", "warning")
        return redirect(url_for("auth.manage_users"))

    picker = Pickster.query.get_or_404(int(picker_id))

    if AppUser.query.filter_by(email=email).first():
        flash(f"A user with email {email} already exists.", "warning")
        return redirect(url_for("auth.manage_users"))

    # Derive user_id from picker name (lower, first word)
    derived_user_id = picker.name.split()[0].lower() if picker.name else None

    user = AppUser(
        email=email,
        user_id=derived_user_id,
        display_name=picker.name,
        roles=roles if roles else ["warehouse"],
        is_active=True,
    )
    db.session.add(user)
    db.session.commit()
    flash(f"Imported {picker.name} as {email}.", "success")
    return redirect(url_for("auth.manage_users"))
