"""Explicit operator-only creation of a new, role-less supplier account.
Run only after backup/migration. Never modifies an existing account.
"""
import argparse
import secrets
import sys
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--factory", required=True)
    parser.add_argument("--actor", required=True, help="Existing authorized internal administrator login name")
    parser.add_argument("--apply", action="store_true", help="Actually create the account; otherwise validate only")
    args = parser.parse_args()
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.auth import AuthUser, AuthAuditLog
    from app.services.auth import build_auth_context, make_password_hash, now_text
    from app.services.carton_supplier_portal import internal_permission, fixed_supplier, save_member
    from app.schemas.carton_supplier_portal import MemberSave
    if not args.username.strip() or len(args.username) > 64 or not args.display_name.strip() or len(args.display_name) > 128:
        parser.error("Invalid account name")
    with SessionLocal() as db:
        actor = db.scalar(select(AuthUser).where(AuthUser.username == args.actor, AuthUser.status == "active"))
        if not actor:
            parser.error("Authorized actor account not found")
        context = build_auth_context(db, actor)
        internal_permission(context, args.factory, "carton_procurement:master_manage", "carton_procurement:order_adjust")
        fixed_supplier(db, args.factory)
        if db.scalar(select(AuthUser).where(AuthUser.username == args.username)):
            parser.error("Account already exists; use reviewed member binding instead")
        if not args.apply:
            print("Validated: new role-less supplier account; use --apply to create after backup/migration.")
            return
        password = secrets.token_urlsafe(24)
        salt, digest = make_password_hash(password)
        user = AuthUser(id=f"user-supplier-{uuid4().hex}", username=args.username, display_name=args.display_name,
            password_salt=salt, password_hash=digest, status="active", force_password_change=1,
            created_at=now_text(), updated_at=now_text())
        try:
            db.add(user); db.flush()
            db.add(AuthAuditLog(user_id=actor.id, username=actor.username, action="supplier_account_created",
                detail=f"new_user_id={user.id}; factory={args.factory}; no internal roles", created_at=now_text()))
            db.flush()
            save_member(db, context, MemberSave(factory_id=args.factory, username=args.username,
                expected_revision=0, reason="受控运维开通供应商账号"))
        except Exception:
            db.rollback()
            raise
        print(f"Created {args.username}; first login must change password. No internal roles assigned.")
        print("Temporary password (deliver privately, do not retain logs): " + password)

if __name__ == "__main__":
    main()
