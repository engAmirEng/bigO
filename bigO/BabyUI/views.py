import logging

from asgiref.sync import sync_to_async

from bigO.proxy_manager import models as proxy_manager_models
from bigO.utils.inertia import inertia, prop_messages
from django.contrib import messages
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth import alogin as auth_login
from django.contrib.auth import alogout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)


def aaa(request):
    return render(request, "BabyUI/aaa.html", {})


def get_redirect_url(
    request, success_url_allowed_hosts: set | None = None, redirect_field_name=REDIRECT_FIELD_NAME
) -> str | None:
    success_url_allowed_hosts = success_url_allowed_hosts or set()
    redirect_to = request.POST.get(redirect_field_name, request.GET.get(redirect_field_name))
    url_is_safe = url_has_allowed_host_and_scheme(
        url=redirect_to,
        allowed_hosts={request.get_host(), *success_url_allowed_hosts},
        require_https=request.is_secure(),
    )
    return redirect_to if url_is_safe else None


@inertia("Auth/SignIn", layout="BabyUI/page.html")
@prop_messages()
async def signin(request):
    errors = {}
    if request.POST:
        form = AuthenticationForm(data=request.POST, request=request)
        if await sync_to_async(form.is_valid)():
            user = form.get_user()
            await auth_login(request, user)
            redirect_url = get_redirect_url(request) or reverse("BabyUI:index")
            return HttpResponseRedirect(redirect_url)
        else:
            errors = form.errors

    return {"errors": errors}


@require_POST
async def logout(request):
    await alogout(request)
    messages.add_message(request, level=messages.SUCCESS, message=gettext("you successfully logged out."))
    return redirect("BabyUI:signin")


@login_required(login_url=reverse_lazy("BabyUI:signin"))
@inertia("Home/Index", layout="BabyUI/page.html")
async def index(request):
    user = await request.auser()
    return {"title": f"hello {user.username}"}


CURRENT_AGENCY_KEY = "current_agency"


@login_required(login_url=reverse_lazy("BabyUI:signin"))
@inertia("Home/Dashboard", layout="BabyUI/page.html")
async def dashboard(request):
    user = await request.auser()
    agent_accounts_qs = proxy_manager_models.Agent.objects.filter(user=user, is_active=True).select_related("agency")
    agent_accounts = [i async for i in agent_accounts_qs[:9]]
    if not agent_accounts:
        messages.add_message(request, messages.ERROR, gettext("you do not have access to any Agency"))
        return redirect("BabyUI:signin")
    if request.POST.get("set_to_agency_id"):
        set_to_agency_id = request.POST["set_to_agency_id"]
        if agent_accounts_qs.filter(agency_id=set_to_agency_id).aexists():
            await request.session.aset(CURRENT_AGENCY_KEY, set_to_agency_id)
        else:
            messages.add_message(request, messages.ERROR, gettext("you cannot access this agency."))
    current_agency_id = await request.session.aget(CURRENT_AGENCY_KEY)
    if not current_agency_id or not await agent_accounts_qs.filter(agency_id=current_agency_id).aexists():
        current_agency_id = agent_accounts[0].id
        await request.session.aset(CURRENT_AGENCY_KEY, current_agency_id)
    return {
        "current_agency_id": current_agency_id,
        "agencies": [{"id": i.agency.id, "name": i.agency.name} for i in agent_accounts],
        "logout_url": reverse("BabyUI:logout"),
    }
