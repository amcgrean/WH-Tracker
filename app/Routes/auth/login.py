from datetime import datetime

from flask import (
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
)
from app.extensions import db
from app.Models.models import AppUser
from app.Services.otp_service import generate_otp, send_otp_email, verify_otp
from app.Routes.auth import auth_bp


# ---------------------------------------------------------------------------
# Login — step 1: enter email
# ---------------------------------------------------------------------------

@auth_bp.route("/login", methods=["GET", "POST"])
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

@auth_bp.route("/verify", methods=["GET", "POST"])
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


@auth_bp.route("/resend", methods=["POST"])
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

@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))
