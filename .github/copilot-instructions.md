# NannyLoop - AI Coding Agent Instructions

## Project Overview
**NannyLoop** is a Flask-based household management system for tracking childcare activities. It enables parents to manage children profiles and activity logs (feeding, diaper changes, etc.) and invite carers to participate in a shared household.

**Architecture**: Monolithic Flask app with SQLite backend, Jinja2 templates for UI, no frontend framework.

## Data Model & Key Patterns

### Core Entities
- **Household**: Central aggregation unit (many parents/carers, multiple children, activity logs)
- **User**: Two roles - `"parent"` (creates households, invites) or `"carer"` (joins via invite code)
- **Child**: Belongs to household; stores name and DOB as string
- **LogEntry**: Activity records tied to child+household; timestamp auto-set to UTC
- **InviteCode**: Time-limited (default 48h), single-use tokens generated with `secrets.token_urlsafe(16)`

### Critical Patterns
- **Household-scoped queries**: Always filter by `household_id` to prevent cross-household data leaks (see `add_log()` validation)
- **Role-based access**: Use `@role_required("parent")` decorator for parent-only endpoints
- **Password security**: Use werkzeug's `generate_password_hash` / `check_password_hash`, never store plaintext
- **Timestamps**: Use `db.func.now()` for server-side UTC dates (avoids client timezone issues)

## File Structure

| Path | Purpose |
|------|---------|
| [backend/app.py](backend/app.py) | Flask routes, auth, household operations |
| [backend/models.py](backend/models.py) | SQLAlchemy ORM models, invite code generation |
| [backend/templates/index.html](backend/templates/index.html) | Dashboard UI with role-specific sections |

## Common Development Tasks

### Running the App
```bash
# From workspace root
python -m flask --app backend.app run
# or: python backend/app.py (sets debug=True, port 5000)
```

### Database Management
- DB file: `nannyloop.db` (SQLite, created at first run via `db.create_all()`)
- Reset DB: Delete `nannyloop.db` and restart app
- Use `db.session.commit()` after adds/updates; `query.first()` or `.all()` for reads

### Adding Routes
1. Create function with `@app.route()` decorator
2. Use `@login_required` for authentication gates
3. Add `@role_required("parent")` for role checks
4. Query via `current_user.household_id` for scoping
5. Flash messages: `flash("text", "error"|"success")`

## Key Integration Points

- **Flask-Login**: User loader at `User.get_id()` (returns string ID); session stored server-side
- **Invite Workflow**: Parent creates code → carer uses code at registration → code marked `used_at` + linked to new user
- **Form Handling**: All forms use `request.form` with `.strip()` normalization; no API endpoints yet
- **Flash Messages**: Rendered in templates via Jinja2; use for all user feedback

## Security & Validation Notes

- **Email normalization**: Always `.strip().lower()` on email input
- **Duplicate prevention**: Check `User.query.filter_by(email=...)` before creating user
- **Invite validation**: `is_valid()` checks expiry and used_at status before allowing registration
- **Household isolation**: Always validate `Child` belongs to `current_user.household_id` in add_log, add_child

## Conventions This Project Uses (Non-Standard)

- Date fields stored as **strings** (e.g., Child.date_of_birth), not datetime objects
- No API layer yet; all communication via form POST/GET
- No request validation library (flask-validator); manual `.strip()` and `isdigit()` checks
- No error codes/logging; uses flash messages for all feedback

---
**Python**: 3.11.7 | **Key Dependencies**: Flask 3.1.2, Flask-Login 0.6.3, SQLAlchemy 2.0.46
