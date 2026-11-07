from functools import wraps

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import InviteForm, SignupForm, TaskForm
from .models import Invite, Membership, Task, Workspace
from .plans import PLANS, limit, within


def _current_membership(request):
    """The user's active workspace membership. Only the user's own memberships
    are ever considered, so a forged session value cannot reach another tenant."""
    qs = request.user.memberships.select_related("workspace")
    m = qs.filter(workspace_id=request.session.get("workspace_id")).first() or qs.first()
    if m is None:  # e.g. a superuser created on the command line
        ws = Workspace.objects.create(name=f"{request.user.get_username()}'s workspace")
        m = Membership.objects.create(user=request.user, workspace=ws, role=Membership.OWNER)
    request.session["workspace_id"] = m.workspace_id
    return m


def workspace_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        request.membership = _current_membership(request)
        request.workspace = request.membership.workspace
        return view(request, *args, **kwargs)

    return wrapper


def owner_required(view):
    @wraps(view)
    @workspace_required
    def wrapper(request, *args, **kwargs):
        if not request.membership.is_owner:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def _usage(ws):
    plan = ws.plan
    members = ws.memberships.count()
    pending = ws.invites.filter(accepted=False).count()
    tasks = ws.tasks.count()
    return {
        "plan": PLANS[plan]["label"],
        "members": members,
        "pending": pending,
        "max_members": limit(plan, "max_members"),
        "tasks": tasks,
        "max_tasks": limit(plan, "max_tasks"),
    }


def signup(request):
    nxt = request.GET.get("next", "")
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            ws = Workspace.objects.create(name=f"{user.get_username()}'s workspace")
            Membership.objects.create(user=user, workspace=ws, role=Membership.OWNER)
            login(request, user)
            request.session["workspace_id"] = ws.pk
            if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
                return redirect(nxt)
            return redirect("dashboard")
    else:
        form = SignupForm()
    return render(request, "registration/signup.html", {"form": form, "next": nxt})


@workspace_required
def dashboard(request):
    ws = request.workspace
    return render(request, "teamspace/dashboard.html", {
        "tasks": ws.tasks.select_related("created_by"),
        "form": TaskForm(),
        "usage": _usage(ws),
    })


@workspace_required
@require_POST
def task_add(request):
    ws = request.workspace
    form = TaskForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter a task title.")
    elif not within(ws.plan, "max_tasks", ws.tasks.count()):
        messages.error(request, "Task limit reached on the Free plan. Upgrade on the Billing page.")
    else:
        Task.objects.create(workspace=ws, title=form.cleaned_data["title"], created_by=request.user)
    return redirect("dashboard")


@workspace_required
@require_POST
def task_toggle(request, pk):
    task = get_object_or_404(Task, pk=pk, workspace=request.workspace)
    task.done = not task.done
    task.save(update_fields=["done"])
    return redirect("dashboard")


@workspace_required
@require_POST
def task_delete(request, pk):
    get_object_or_404(Task, pk=pk, workspace=request.workspace).delete()
    return redirect("dashboard")


@workspace_required
def team(request):
    ws = request.workspace
    return render(request, "teamspace/team.html", {
        "members": ws.memberships.select_related("user").order_by("role", "user__username"),
        "invites": ws.invites.filter(accepted=False),
        "form": InviteForm(),
        "usage": _usage(ws),
    })


@owner_required
@require_POST
def invite_create(request):
    ws = request.workspace
    form = InviteForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter a valid email address.")
        return redirect("team")
    email = form.cleaned_data["email"].strip().lower()
    used = ws.memberships.count() + ws.invites.filter(accepted=False).count()
    if not within(ws.plan, "max_members", used):
        messages.error(request, "Member limit reached for this plan. Upgrade on the Billing page.")
    elif ws.memberships.filter(user__email__iexact=email).exists():
        messages.error(request, "That person is already a member.")
    elif ws.invites.filter(email__iexact=email, accepted=False).exists():
        messages.error(request, "That email already has a pending invite.")
    else:
        inv = Invite.objects.create(workspace=ws, email=email, invited_by=request.user)
        link = request.build_absolute_uri(inv.get_absolute_url())
        send_mail(f"Join {ws.name}", f"{request.user.get_username()} invited you to {ws.name}: {link}",
                  None, [email])
        messages.success(request, f"Invite created for {email}. Link: {link}")
    return redirect("team")


@owner_required
@require_POST
def member_remove(request, pk):
    m = get_object_or_404(Membership, pk=pk, workspace=request.workspace)
    if m.is_owner:
        messages.error(request, "The owner cannot be removed.")
    else:
        m.delete()
    return redirect("team")


@login_required
def accept_invite(request, token):
    inv = get_object_or_404(Invite, token=token, accepted=False)
    ws = inv.workspace
    wrong_email = (request.user.email or "").lower() != inv.email.lower()
    if request.method == "POST" and not wrong_email:
        if ws.memberships.filter(user=request.user).exists():
            messages.info(request, "You are already a member.")
        elif not within(ws.plan, "max_members", ws.memberships.count()):
            messages.error(request, "This workspace has reached its member limit.")
            return redirect("dashboard")
        else:
            Membership.objects.create(user=request.user, workspace=ws, role=Membership.MEMBER)
            inv.accepted = True
            inv.save(update_fields=["accepted"])
            request.session["workspace_id"] = ws.pk
            messages.success(request, f"You joined {ws.name}.")
        return redirect("dashboard")
    return render(request, "teamspace/invite_accept.html", {"invite": inv, "wrong_email": wrong_email})


@owner_required
def billing(request):
    ws = request.workspace
    if request.method == "POST":
        new = request.POST.get("plan")
        if new not in PLANS:
            raise PermissionDenied
        members, tasks = ws.memberships.count(), ws.tasks.count()
        cap_m, cap_t = limit(new, "max_members"), limit(new, "max_tasks")
        if cap_m is not None and members > cap_m:
            messages.error(request, f"Remove members first: {members} members, the {PLANS[new]['label']} plan allows {cap_m}.")
        elif cap_t is not None and tasks > cap_t:
            messages.error(request, f"Delete tasks first: {tasks} tasks, the {PLANS[new]['label']} plan allows {cap_t}.")
        else:
            ws.plan = new
            ws.save(update_fields=["plan"])
            messages.success(request, f"Plan changed to {PLANS[new]['label']} (simulated, no payment taken).")
        return redirect("billing")
    return render(request, "teamspace/billing.html", {"plans": PLANS, "usage": _usage(ws)})


@login_required
@require_POST
def switch_workspace(request):
    m = request.user.memberships.filter(workspace_id=request.POST.get("workspace")).first()
    if m:
        request.session["workspace_id"] = m.workspace_id
    return redirect("dashboard")
