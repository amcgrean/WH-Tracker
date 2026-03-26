"""
auth_routes.py
--------------
Blueprint: auth  (prefix /auth)

Public routes:
    GET  /auth/login          — email entry form
    POST /auth/login          — send OTP
    GET  /auth/verify         — code entry form
    POST /auth/verify         — validate code, create session
    POST /auth/logout         — clear session

Admin-only routes (require 'admin' role):
    GET  /auth/users          — list all AppUsers
    GET  /auth/users/add      — add user form
    POST /auth/users/add      — create user
    GET  /auth/users/<id>/edit  — edit user form
    POST /auth/users/<id>/edit  — save user changes
    POST /auth/users/<id>/toggle — toggle active/inactive
    POST /auth/users/<id>/delete — delete user

Phase 2 note: add /auth/login-phone and /auth/verify-phone routes here.
"""

from datetime import datetime

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.auth import (
    SESSION_USER_EMAIL,
    SESSION_USER_ID,
    SESSION_USER_NAME,
    SESSION_USER_REP_ID,
    SESSION_USER_ROLES,
    login_required,
    role_required,
)
from app.extensions import db
from app.Models.models import AppUser, OTPCode, Pickster
from app.Services.otp_service import generate_otp, send_otp_email, verify_otp

auth = Blueprint("auth", __name__, url_prefix="/auth")

AVAILABLE_ROLES = [
    "admin",
    "ops",
    "warehouse",
    "supervisor",
    "production",
    "delivery",
    "dispatch",
    "sales",
    "credits",
    "purchasing",
]


# ---------------------------------------------------------------------------
# Login — step 1: enter email
# ---------------------------------------------------------------------------

@auth.route("/login", methods=["GET", "POST"])
def login():
    if session.get(SESSION_USER_ID):
        return redirect(url_for("main.work_center"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        if not email:
            flash("Please enter your email address.", "warning")
            return render_template("auth/login.html")

        # Look up user
        user = AppUser.query.filter_by(email=email, is_active=True).first()
        if not user:
            # Deliberate vague message — don't reveal whether email exists
            flash("If that address is registered, you'll receive a code shortly.", "info")
            return render_template("auth/login.html")

        code, err = generate_otp(email)
        if err:
            flash(err, "warning")
            return render_template("auth/login.html")

        ok, msg = send_otp_email(email, code)
        if not ok:
            flash(f"Could not send code: {msg}", "danger")
            return render_template("auth/login.html")

        # Store email in session so verify step knows who we're verifying
        session["otp_pending_email"] = email
        flash("A sign-in code has been sent to your email.", "info")
        return redirect(url_for("auth.verify"))

    return render_template("auth/login.html")


# ---------------------------------------------------------------------------
# Verify — step 2: enter OTP code
# ---------------------------------------------------------------------------

@auth.route("/verify", methods=["GET", "POST"])
def verify():
    if session.get(SESSION_USER_ID):
        return redirect(url_for("main.work_center"))

    pending_email = session.get("otp_pending_email", "")

    if request.method == "POST":
        email = (request.form.get("email") or pending_email or "").strip().lower()
        code = (request.form.get("code") or "").strip()

        if not email or not code:
            flash("Email and code are required.", "warning")
            return render_template("auth/verify.html", email=email)

        ok, msg = verify_otp(email, code)
        if not ok:
            flash(msg, "danger")
            return render_template("auth/verify.html", email=email)

        user = AppUser.query.filter_by(email=email, is_active=True).first()
        if not user:
            flash("Account not found or deactivated.", "danger")
            return redirect(url_for("auth.login"))

        # Create session
        session.permanent = True
        session[SESSION_USER_ID]    = user.id
        session[SESSION_USER_EMAIL] = user.email
        session[SESSION_USER_REP_ID] = user.user_id or ""
        session[SESSION_USER_NAME]  = user.display_name or user.email.split("@")[0]
        session[SESSION_USER_ROLES] = user.roles or []
        session.pop("otp_pending_email", None)

        # Update last login timestamp
        user.last_login_at = datetime.utcnow()
        db.session.commit()

        next_url = request.args.get("next") or url_for("main.work_center")
        return redirect(next_url)

    return render_template("auth/verify.html", email=pending_email)


@auth.route("/resend", methods=["POST"])
def resend():
    email = (request.form.get("email") or session.get("otp_pending_email", "")).strip().lower()
    if not email:
        flash("No email address to resend to.", "warning")
        return redirect(url_for("auth.login"))

    user = AppUser.query.filter_by(email=email, is_active=True).first()
    if not user:
        flash("If that address is registered, you'll receive a code shortly.", "info")
        return redirect(url_for("auth.verify"))

    code, err = generate_otp(email)
    if err:
        flash(err, "warning")
        return redirect(url_for("auth.verify"))

    ok, msg = send_otp_email(email, code)
    if ok:
        session["otp_pending_email"] = email
        flash("A new code has been sent.", "info")
    else:
        flash(f"Could not send code: {msg}", "danger")

    return redirect(url_for("auth.verify"))


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@auth.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))


# ---------------------------------------------------------------------------
# Admin — User Management
# ---------------------------------------------------------------------------

@auth.route("/users")
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


@auth.route("/users/add", methods=["GET", "POST"])
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


@auth.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
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


@auth.route("/users/<int:user_id>/toggle", methods=["POST"])
@role_required("admin")
def toggle_user(user_id):
    user = AppUser.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()
    state = "activated" if user.is_active else "deactivated"
    flash(f"User {user.email} {state}.", "success")
    return redirect(url_for("auth.manage_users"))


@auth.route("/users/<int:user_id>/delete", methods=["POST"])
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


@auth.route("/users/import-picker", methods=["POST"])
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
