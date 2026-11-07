from django.contrib import admin

from .models import Invite, Membership, Task, Workspace

admin.site.register([Workspace, Membership, Invite, Task])
