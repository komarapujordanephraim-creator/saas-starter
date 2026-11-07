# Teamspace: a small multi-tenant SaaS starter

A Django 5 starter for the parts every B2B SaaS needs before the actual product: sign-up that creates a workspace, team invites, roles, plan limits and a billing page. The "product" inside is a simple shared task list so the multi-tenant behaviour can be seen and tested. It is a portfolio project and a starting point, not a finished product.

## What it does

- **Workspaces (tenants).** Signing up creates a workspace and makes you its owner. A user can belong to several workspaces and switch between them.
- **Roles.** Owner and Member. Only owners can invite, remove members or change the plan.
- **Team invites.** The owner invites by email. The invite is a one-time link and works only for the account with that email address. Emails print to the server console in development.
- **Plans and limits.** Free (3 members, 10 tasks) and Pro (10 members, unlimited tasks). Limits are enforced on the server when adding tasks, inviting and accepting invites. Pending invites count against the member limit. A downgrade is blocked if the workspace is over the lower plan's limits.
- **Tenant isolation.** Every query for tenant data is filtered by the active workspace, and the active workspace is always resolved from the user's own memberships, so a forged session value cannot reach another tenant.

## Run it

```
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
python manage.py test
```

Open http://127.0.0.1:8000/ and sign up. Settings read `DJANGO_SECRET_KEY`, `DJANGO_DEBUG` and `DJANGO_ALLOWED_HOSTS` from the environment. The defaults are for local development only.

## Tests

20 tests cover sign-up, login-required pages, tenant isolation (read, toggle, delete, forged session, switching), plan limits, downgrade rules, invite rules (wrong email, reuse, member limit) and role checks. I also broke the isolation filter on purpose to confirm the isolation test fails.

## Not included (be aware before using it for real)

- **No real billing.** The Billing page is simulated: plan changes are saved but no payment is taken. To go live, add Stripe Checkout and a webhook that sets `Workspace.plan`.
- **No real email.** Invites use Django's console email backend. Configure SMTP or an email service for production.
- **No password reset, email verification, rate limiting or audit log.**
- SQLite database. Use PostgreSQL for anything real.
- Two roles only, and one task model as the example product.

## Structure

- `teamspace/plans.py`: plan definitions and limit helper
- `teamspace/models.py`: Workspace, Membership, Invite, Task
- `teamspace/views.py`: workspace resolution, owner checks, limit enforcement
- `teamspace/tests.py`: the 20 tests

MIT License. Built by Komarapu Jordan Ephraim.
