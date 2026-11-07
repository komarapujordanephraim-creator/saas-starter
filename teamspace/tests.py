from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Invite, Membership, Task, Workspace

User = get_user_model()


def make_user(name, email=None):
    u = User.objects.create_user(name, email or f"{name}@example.com", "pw-12345-test")
    ws = Workspace.objects.create(name=f"{name} ws")
    Membership.objects.create(user=u, workspace=ws, role=Membership.OWNER)
    return u, ws


class SignupTests(TestCase):
    def test_signup_creates_workspace_and_owner(self):
        r = self.client.post(reverse("signup"), {
            "username": "newbie", "email": "new@example.com",
            "password1": "S0me-long-pass!", "password2": "S0me-long-pass!"})
        self.assertRedirects(r, reverse("dashboard"))
        m = Membership.objects.get(user__username="newbie")
        self.assertTrue(m.is_owner)
        self.assertEqual(m.workspace.plan, "free")

    def test_duplicate_email_rejected(self):
        make_user("a", "same@example.com")
        r = self.client.post(reverse("signup"), {
            "username": "b", "email": "SAME@example.com",
            "password1": "S0me-long-pass!", "password2": "S0me-long-pass!"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(username="b").exists())

    def test_pages_require_login(self):
        for name in ("dashboard", "team", "billing"):
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 302)
            self.assertIn("/login/", r["Location"])


class TenantIsolationTests(TestCase):
    def setUp(self):
        self.a, self.ws_a = make_user("alice")
        self.b, self.ws_b = make_user("bob")
        self.task_a = Task.objects.create(workspace=self.ws_a, title="alice secret", created_by=self.a)

    def test_other_tenant_cannot_see_task(self):
        self.client.force_login(self.b)
        r = self.client.get(reverse("dashboard"))
        self.assertNotContains(r, "alice secret")

    def test_other_tenant_cannot_toggle_or_delete(self):
        self.client.force_login(self.b)
        self.assertEqual(self.client.post(reverse("task_toggle", args=[self.task_a.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("task_delete", args=[self.task_a.pk])).status_code, 404)
        self.task_a.refresh_from_db()
        self.assertFalse(self.task_a.done)

    def test_forged_session_workspace_does_not_leak(self):
        self.client.force_login(self.b)
        s = self.client.session
        s["workspace_id"] = self.ws_a.pk
        s.save()
        r = self.client.get(reverse("dashboard"))
        self.assertNotContains(r, "alice secret")

    def test_cannot_switch_into_foreign_workspace(self):
        self.client.force_login(self.b)
        self.client.post(reverse("switch_workspace"), {"workspace": self.ws_a.pk})
        self.assertNotContains(self.client.get(reverse("dashboard")), "alice secret")

    def test_get_not_allowed_for_state_changes(self):
        self.client.force_login(self.a)
        self.assertEqual(self.client.get(reverse("task_toggle", args=[self.task_a.pk])).status_code, 405)


class PlanLimitTests(TestCase):
    def setUp(self):
        self.u, self.ws = make_user("owner")
        self.client.force_login(self.u)

    def test_free_plan_task_limit(self):
        for i in range(12):
            self.client.post(reverse("task_add"), {"title": f"t{i}"})
        self.assertEqual(self.ws.tasks.count(), 10)

    def test_pro_plan_has_no_task_limit(self):
        self.ws.plan = "pro"
        self.ws.save()
        for i in range(12):
            self.client.post(reverse("task_add"), {"title": f"t{i}"})
        self.assertEqual(self.ws.tasks.count(), 12)

    def test_free_plan_member_limit_counts_pending_invites(self):
        # owner is 1 of 3, so two invites fit and the third is refused
        for e in ("a@x.com", "b@x.com", "c@x.com"):
            self.client.post(reverse("invite_create"), {"email": e})
        self.assertEqual(self.ws.invites.count(), 2)

    def test_downgrade_blocked_when_over_limit(self):
        self.ws.plan = "pro"
        self.ws.save()
        for i in range(11):
            Task.objects.create(workspace=self.ws, title=f"t{i}", created_by=self.u)
        self.client.post(reverse("billing"), {"plan": "free"})
        self.ws.refresh_from_db()
        self.assertEqual(self.ws.plan, "pro")

    def test_downgrade_allowed_when_within_limit(self):
        self.ws.plan = "pro"
        self.ws.save()
        self.client.post(reverse("billing"), {"plan": "free"})
        self.ws.refresh_from_db()
        self.assertEqual(self.ws.plan, "free")

    def test_unknown_plan_rejected(self):
        r = self.client.post(reverse("billing"), {"plan": "enterprise"})
        self.assertEqual(r.status_code, 403)


class RoleAndInviteTests(TestCase):
    def setUp(self):
        self.owner, self.ws = make_user("owner")
        self.guest = User.objects.create_user("guest", "guest@example.com", "pw-12345-test")
        self.guest_ws = Workspace.objects.create(name="guest ws")
        Membership.objects.create(user=self.guest, workspace=self.guest_ws, role=Membership.OWNER)

    def _invite(self, email="guest@example.com"):
        return Invite.objects.create(workspace=self.ws, email=email, invited_by=self.owner)

    def test_invite_flow_adds_member(self):
        inv = self._invite()
        self.client.force_login(self.guest)
        self.client.post(reverse("accept_invite", args=[inv.token]))
        self.assertTrue(Membership.objects.filter(user=self.guest, workspace=self.ws, role="member").exists())
        inv.refresh_from_db()
        self.assertTrue(inv.accepted)

    def test_invite_for_other_email_is_refused(self):
        inv = self._invite("someone-else@example.com")
        self.client.force_login(self.guest)
        self.client.post(reverse("accept_invite", args=[inv.token]))
        self.assertFalse(Membership.objects.filter(user=self.guest, workspace=self.ws).exists())

    def test_invite_cannot_be_reused(self):
        inv = self._invite()
        self.client.force_login(self.guest)
        self.client.post(reverse("accept_invite", args=[inv.token]))
        self.assertEqual(self.client.get(reverse("accept_invite", args=[inv.token])).status_code, 404)

    def test_invite_respects_member_limit(self):
        for i in range(2):  # owner + 2 = 3, the Free limit
            u = User.objects.create_user(f"m{i}", f"m{i}@example.com", "pw-12345-test")
            Membership.objects.create(user=u, workspace=self.ws)
        inv = self._invite()
        self.client.force_login(self.guest)
        self.client.post(reverse("accept_invite", args=[inv.token]))
        self.assertFalse(Membership.objects.filter(user=self.guest, workspace=self.ws).exists())

    def test_member_cannot_invite_bill_or_remove(self):
        Membership.objects.create(user=self.guest, workspace=self.ws)
        self.client.force_login(self.guest)
        s = self.client.session
        s["workspace_id"] = self.ws.pk
        s.save()
        self.assertEqual(self.client.post(reverse("invite_create"), {"email": "x@y.com"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("billing"), {"plan": "pro"}).status_code, 403)
        owner_m = Membership.objects.get(user=self.owner, workspace=self.ws)
        self.assertEqual(self.client.post(reverse("member_remove", args=[owner_m.pk])).status_code, 403)

    def test_owner_cannot_be_removed(self):
        self.client.force_login(self.owner)
        owner_m = Membership.objects.get(user=self.owner, workspace=self.ws)
        self.client.post(reverse("member_remove", args=[owner_m.pk]))
        self.assertTrue(Membership.objects.filter(pk=owner_m.pk).exists())
