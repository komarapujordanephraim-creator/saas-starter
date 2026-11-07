from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("signup/", views.signup, name="signup"),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("tasks/add/", views.task_add, name="task_add"),
    path("tasks/<int:pk>/toggle/", views.task_toggle, name="task_toggle"),
    path("tasks/<int:pk>/delete/", views.task_delete, name="task_delete"),
    path("team/", views.team, name="team"),
    path("team/invite/", views.invite_create, name="invite_create"),
    path("team/members/<int:pk>/remove/", views.member_remove, name="member_remove"),
    path("invite/<str:token>/", views.accept_invite, name="accept_invite"),
    path("billing/", views.billing, name="billing"),
    path("workspace/switch/", views.switch_workspace, name="switch_workspace"),
]
