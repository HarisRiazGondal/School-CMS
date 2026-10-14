from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import active_school_memberships


@login_required
def home(request):
    return render(request, "accounts/home.html", {
        "memberships": active_school_memberships(request.user),
    })
