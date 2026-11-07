import secrets

from django.conf import settings
from django.db import models
from django.urls import reverse

from .plans import PLAN_CHOICES


class Workspace(models.Model):
    name = models.CharField(max_length=80)
    plan = models.CharField(max_length=10, choices=PLAN_CHOICES, default="free")
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Membership(models.Model):
    OWNER, MEMBER = "owner", "member"
    ROLES = [(OWNER, "Owner"), (MEMBER, "Member")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=ROLES, default=MEMBER)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "workspace"], name="one_membership_per_user")]

    def __str__(self):
        return f"{self.user} in {self.workspace} ({self.role})"

    @property
    def is_owner(self):
        return self.role == self.OWNER


def _token():
    return secrets.token_urlsafe(24)


class Invite(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="invites")
    email = models.EmailField()
    token = models.CharField(max_length=64, unique=True, default=_token, editable=False)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    accepted = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    def get_absolute_url(self):
        return reverse("accept_invite", args=[self.token])


class Task(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=140)
    done = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["done", "-created"]

    def __str__(self):
        return self.title
