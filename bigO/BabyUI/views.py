import asyncio
import logging
from datetime import timedelta
from functools import wraps

import pydantic
from asgiref.sync import sync_to_async

from bigO.proxy_manager import models as proxy_manager_models
from bigO.proxy_manager import services as proxy_manager_services
from bigO.utils.inertia import inertia, prop_messages
from django.contrib import messages
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth import alogin as auth_login
from django.contrib.auth import alogout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.core.paginator import Paginator
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
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


def prop_urls():
    def decorator(func):
        urls = [{"name": i, "url": reverse_lazy(i)} for i in {"BabyUI:dashboard_home", "BabyUI:dashboard_users"}]
        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def inner(request, *args, **kwargs):
                props = await func(request, *args, **kwargs)
                # if something other than a dict is returned, the user probably wants to return a specific response
                if not isinstance(props, dict):
                    return props
                props["urls"] = urls
                return props

        else:

            @wraps(func)
            def inner(request, *args, **kwargs):
                props = func(request, *args, **kwargs)
                # if something other than a dict is returned, the user probably wants to return a specific response
                if not isinstance(props, dict):
                    return props
                props["urls"] = urls
                return props

        return inner

    return decorator


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
@prop_urls()
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
    if not current_agency_id or not (
        agent_obj := await agent_accounts_qs.filter(agency_id=current_agency_id).afirst()
    ):
        current_agency_id = agent_accounts[0].id
        agent_obj = await agent_accounts_qs.filter(agency_id=current_agency_id).afirst()
        await request.session.aset(CURRENT_AGENCY_KEY, current_agency_id)

    users_qs = proxy_manager_services.get_agent_current_subscriptionperiods_qs(agent=agent_obj)
    users_qs = users_qs.select_related("profile").ann_expires_at().ann_total_limit_bytes().order_by("-pk")
    if search_qs := request.GET.get("search"):
        users_qs = users_qs.filter(profile__title__icontains=search_qs)
    users_qs = users_qs.distinct()
    users_paginator = Paginator(users_qs, request.GET.get("pageSize", 25))
    users_page_number = request.GET.get("users_page_number", request.GET.get("page", 1))
    users_page = await sync_to_async(users_paginator.get_page)(users_page_number)

    return {
        "current_agency_id": current_agency_id,
        "agencies": [{"id": i.agency.id, "name": i.agency.name} for i in agent_accounts],
        "logout_url": reverse("BabyUI:logout"),
        "users_list_page": {
            "num_pages": users_page.paginator.num_pages,
            "num_records": users_page.paginator.count,
            "num_per_page": users_page.paginator.per_page,
            "current_page_num": users_page.number,
            "search_qs": search_qs,
            "users": [
                {
                    "id": str(i.profile_id),
                    "title": i.profile.title,
                    "last_usage_at_repr": naturaltime(i.last_usage_at),
                    "online_status": "online"
                    if i.last_usage_at and (timezone.now() - i.last_usage_at < timedelta(minutes=2))
                    else "offline"
                    if i.last_usage_at
                    else "never",
                    "used_bytes": i.current_download_bytes + i.current_upload_bytes,
                    "total_limit_bytes": i.total_limit_bytes,
                    "expires_in_seconds": (i.expires_at - timezone.now()).total_seconds(),
                }
                for i in await sync_to_async(list)(users_page)
            ],
        },
    }


@login_required(login_url=reverse_lazy("BabyUI:signin"))
@inertia("Dashboard/Users", layout="BabyUI/page.html")
@prop_urls()
async def dashboard_users(request):
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
    if not current_agency_id or not (
        agent_obj := await agent_accounts_qs.filter(agency_id=current_agency_id).afirst()
    ):
        current_agency_id = agent_accounts[0].id
        agent_obj = await agent_accounts_qs.filter(agency_id=current_agency_id).afirst()
        await request.session.aset(CURRENT_AGENCY_KEY, current_agency_id)

    users_qs = proxy_manager_services.get_agent_current_subscriptionperiods_qs(agent=agent_obj)
    users_qs = users_qs.select_related("profile").ann_expires_at().ann_total_limit_bytes().order_by("-pk")
    if search_qs := request.GET.get("search"):
        users_qs = users_qs.filter(profile__title__icontains=search_qs)
    users_qs = users_qs.distinct()
    users_paginator = Paginator(users_qs, request.GET.get("pageSize", 25))
    users_page_number = request.GET.get("users_page_number", request.GET.get("page", 1))
    users_page = await sync_to_async(users_paginator.get_page)(users_page_number)

    return {
        "current_agency_id": current_agency_id,
        "agencies": [{"id": i.agency.id, "name": i.agency.name} for i in agent_accounts],
        "logout_url": reverse("BabyUI:logout"),
        "users_list_page": {
            "num_pages": users_page.paginator.num_pages,
            "num_records": users_page.paginator.count,
            "num_per_page": users_page.paginator.per_page,
            "current_page_num": users_page.number,
            "search_qs": search_qs,
            "users": [
                {
                    "id": str(i.profile_id),
                    "title": i.profile.title,
                    "last_usage_at_repr": naturaltime(i.last_usage_at),
                    "online_status": "online"
                    if i.last_usage_at and (timezone.now() - i.last_usage_at < timedelta(minutes=2))
                    else "offline"
                    if i.last_usage_at
                    else "never",
                    "used_bytes": i.current_download_bytes + i.current_upload_bytes,
                    "total_limit_bytes": i.total_limit_bytes,
                    "expires_in_seconds": (i.expires_at - timezone.now()).total_seconds(),
                }
                for i in await sync_to_async(list)(users_page)
            ],
        },
    }
