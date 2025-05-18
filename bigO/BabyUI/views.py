import asyncio
import logging
from datetime import timedelta
from functools import wraps

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
from django.db.models import QuerySet
from django.db.models.functions import Coalesce
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext
from django.views.decorators.http import require_POST

from . import utils

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
        current_agency_id = agent_accounts[0].agency_id
        agent_obj = await agent_accounts_qs.aget(agency_id=current_agency_id)
        await request.session.aset(CURRENT_AGENCY_KEY, current_agency_id)

    users_qs = proxy_manager_services.get_agent_current_subscriptionperiods_qs(agent=agent_obj)
    users_qs = users_qs.select_related("profile").ann_expires_at().ann_total_limit_bytes().order_by("-pk")

    async def users_search_callback(queryset: QuerySet[proxy_manager_models.SubscriptionPeriod], q: str):
        return queryset.filter(profile__title__icontains=q)

    async def users_render_record_callback(i: proxy_manager_models.SubscriptionPeriod) -> utils.User:
        return utils.User(
            id=str(i.profile_id),
            title=i.profile.title,
            last_usage_at_repr=naturaltime(i.last_usage_at),
            online_status="online"
            if i.last_usage_at and (timezone.now() - i.last_usage_at < timedelta(minutes=2))
            else "offline"
            if i.last_usage_at
            else "never",
            used_bytes=i.current_download_bytes + i.current_upload_bytes,
            total_limit_bytes=i.total_limit_bytes,
            expires_in_seconds=int((i.expires_at - timezone.now()).total_seconds()),
        )

    async def users_sort_callback(
        queryset: QuerySet[proxy_manager_models.SubscriptionPeriod], orderings: list[tuple[str, bool]]
    ):
        order_bys = []
        res_orderings = []
        for key, is_asc in orderings:
            if key == "used_bytes":
                queryset = queryset.annotate(
                    used_bytes=Coalesce("current_download_bytes", 0) + Coalesce("current_upload_bytes", 0)
                )
                order_bys.append(("" if is_asc else "-") + "used_bytes")
            res_orderings.append((key, is_asc))
        return queryset.order_by(*order_bys), res_orderings

    user_listpagehandler = utils.ListPageHandler[proxy_manager_models.SubscriptionPeriod, utils.User](
        request,
        queryset=users_qs,
        search_callback=users_search_callback,
        render_record_callback=users_render_record_callback,
        sort_callback=users_sort_callback,
        sortables={"used_bytes"},
        prefix="users",
    )
    users_res = await user_listpagehandler.to_response()

    return {
        "current_agency_id": current_agency_id,
        "agencies": [{"id": i.agency.id, "name": i.agency.name} for i in agent_accounts],
        "logout_url": reverse("BabyUI:logout"),
        "users_list_page": users_res.model_dump(),
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
        current_agency_id = agent_accounts[0].agency_id
        agent_obj = await agent_accounts_qs.aget(agency_id=current_agency_id)
        await request.session.aset(CURRENT_AGENCY_KEY, current_agency_id)

    users_qs = proxy_manager_services.get_agent_current_subscriptionperiods_qs(agent=agent_obj)
    users_qs = users_qs.select_related("profile").ann_expires_at().ann_total_limit_bytes().order_by("-pk")

    async def users_search_callback(queryset: QuerySet[proxy_manager_models.SubscriptionPeriod], q: str):
        return queryset.filter(profile__title__icontains=q)

    async def users_render_record_callback(i: proxy_manager_models.SubscriptionPeriod) -> utils.User:
        return utils.User(
            id=str(i.profile_id),
            title=i.profile.title,
            last_usage_at_repr=naturaltime(i.last_usage_at),
            online_status="online"
            if i.last_usage_at and (timezone.now() - i.last_usage_at < timedelta(minutes=2))
            else "offline"
            if i.last_usage_at
            else "never",
            used_bytes=i.current_download_bytes + i.current_upload_bytes,
            total_limit_bytes=i.total_limit_bytes,
            expires_in_seconds=int((i.expires_at - timezone.now()).total_seconds()),
        )

    async def users_sort_callback(
        queryset: QuerySet[proxy_manager_models.SubscriptionPeriod], orderings: list[tuple[str, bool]]
    ):
        order_bys = []
        res_orderings = []
        for key, is_asc in orderings:
            if key == "used_bytes":
                queryset = queryset.annotate(
                    used_bytes=Coalesce("current_download_bytes", 0) + Coalesce("current_upload_bytes", 0)
                )
                order_bys.append(("" if is_asc else "-") + "used_bytes")
            res_orderings.append((key, is_asc))
        return queryset.order_by(*order_bys), res_orderings

    user_listpagehandler = utils.ListPageHandler[proxy_manager_models.SubscriptionPeriod, utils.User](
        request,
        queryset=users_qs,
        search_callback=users_search_callback,
        render_record_callback=users_render_record_callback,
        sort_callback=users_sort_callback,
        sortables={"used_bytes"},
        prefix="users",
    )
    users_res = await user_listpagehandler.to_response()

    return {
        "current_agency_id": current_agency_id,
        "agencies": [{"id": i.agency.id, "name": i.agency.name} for i in agent_accounts],
        "logout_url": reverse("BabyUI:logout"),
        "users_list_page": users_res.model_dump(),
    }
