import asyncio
import logging
from datetime import timedelta
from functools import wraps
from zoneinfo import ZoneInfo

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

from ..utils.templatetags.jformat import jformat
from . import forms, services, utils

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
    return redirect("BabyUI:dashboard_users")
    user = await request.auser()
    return {"title": f"hello {user.username}"}


CURRENT_AGENCY_KEY = "current_agency"


@login_required(login_url=reverse_lazy("BabyUI:signin"))
@inertia("Home/Dashboard", layout="BabyUI/page.html")
@prop_urls()
async def dashboard(request):
    return redirect("BabyUI:dashboard_users")

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


async def users_search_callback(queryset: QuerySet[proxy_manager_models.SubscriptionProfile], q: str):
    return queryset.filter(title__icontains=q)


async def users_render_record_callback(i: proxy_manager_models.SubscriptionProfile) -> utils.User:
    return utils.User(
        id=str(i.id),
        title=i.title,
        last_usage_at_repr=naturaltime(i.last_usage_at),
        last_sublink_at_repr=naturaltime(i.last_sublink_at) if i.last_sublink_at else "never",
        online_status="online"
        if i.last_usage_at and (timezone.now() - i.last_usage_at < timedelta(minutes=2))
        else "offline"
        if i.last_usage_at
        else "never",
        used_bytes=i.current_download_bytes + i.current_upload_bytes,
        total_limit_bytes=i.current_total_limit_bytes,
        expires_in_seconds=int((i.current_expires_at - timezone.now()).total_seconds()),
    )


async def users_sort_callback(
    queryset: QuerySet[proxy_manager_models.SubscriptionProfile], orderings: list[tuple[str, bool]]
):
    order_bys = []
    res_orderings = []
    for key, is_asc in orderings:
        if key == "used_bytes":
            queryset = queryset.annotate(
                used_bytes=Coalesce("current_download_bytes", 0) + Coalesce("current_upload_bytes", 0)
            )
            order_bys.append(("" if is_asc else "-") + "used_bytes")
        elif key == "last_sublink_at":
            order_bys.append(("" if is_asc else "-") + "last_sublink_at")
        elif key == "last_usage_at":
            order_bys.append(("" if is_asc else "-") + "last_usage_at")
        elif key == "expires_at":
            order_bys.append(("" if is_asc else "-") + "current_expires_at")
        res_orderings.append((key, is_asc))
    if order_bys:
        return queryset.order_by(*order_bys), res_orderings
    return queryset, []


@login_required(login_url=reverse_lazy("BabyUI:signin"))
@inertia("Dashboard/Users", layout="BabyUI/page.html")
@prop_urls()
async def dashboard_users(request):
    user = await request.auser()
    # agent
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
    # end

    errors = {}
    # form
    if request.POST and request.POST.get("action") == "new_user":
        newuser_form = forms.NewUserForm(request.POST, prefix="newuser1", agency=agent_obj.agency)
        if await sync_to_async(newuser_form.is_valid)():
            await sync_to_async(services.create_new_user)(
                agency=agent_obj.agency,
                agentuser=request.user,
                plan=newuser_form.cleaned_data["plan"],
                title=newuser_form.cleaned_data["title"],
                description=newuser_form.cleaned_data["description"],
                plan_args=newuser_form.get_plan_args(),
            )
            return redirect(request.path)
        errors.update(**newuser_form.errors)
    else:
        newuser_form = forms.NewUserForm(prefix="newuser1", agency=agent_obj.agency)
    # end

    # users
    users_qs = proxy_manager_services.get_agent_current_subscriptionprofiled_qs(agent=agent_obj)

    users_qs = (
        users_qs.ann_last_usage_at()
        .ann_last_sublink_at()
        .ann_current_period_fields()
        .filter(current_created_at__isnull=False)
        .order_by("-current_created_at")
    )

    user_listpagehandler = utils.ListPageHandler[proxy_manager_models.SubscriptionProfile, utils.User](
        request,
        queryset=users_qs,
        search_callback=users_search_callback,
        render_record_callback=users_render_record_callback,
        sort_callback=users_sort_callback,
        sortables={"used_bytes", "last_sublink_at", "last_usage_at", "expires_at"},
        prefix="users",
    )
    users_res = await user_listpagehandler.to_response()
    # end

    creatable_plans_qs = newuser_form.fields["plan"].queryset
    # user detail
    selected_user = None
    if profile_id := request.GET.get("profile_id"):
        selected_user: proxy_manager_models.SubscriptionProfile = await users_qs.filter(id=profile_id).select_related("initial_agency").afirst()
        selected_user.current_period = (
            await selected_user.periods.filter(selected_as_current=True).select_related("plan").afirst()
        )
        user_events = selected_user.profile_subscriptionevents.all()
        periods_qs = selected_user.periods.ann_expires_at().ann_total_limit_bytes().order_by("-created_at")

        async def periods_render_record_callback(i: proxy_manager_models.SubscriptionPeriod) -> utils.User:
            return utils.Period(
                id=str(i.id),
                last_usage_at_repr=naturaltime(i.last_usage_at),
                last_sublink_at_repr=naturaltime(i.last_sublink_at) if i.last_sublink_at else "never",
                used_bytes=i.current_download_bytes + i.current_upload_bytes,
                total_limit_bytes=i.total_limit_bytes,
                expires_in_seconds=int((i.expires_at - timezone.now()).total_seconds()),
            )

        period_listpagehandler = utils.ListPageHandler[proxy_manager_models.SubscriptionPeriod, utils.User](
            request,
            queryset=periods_qs,
            render_record_callback=periods_render_record_callback,
            prefix="periods",
        )
        periods_res = await period_listpagehandler.to_response()

        # form
        if request.POST and request.POST.get("action") == "renew_user":
            renewuser_form = forms.RenewUserForm(request.POST, profile=selected_user, current_period=selected_user.current_period, prefix="renewuser1")
            if await sync_to_async(renewuser_form.is_valid)():
                await sync_to_async(services.renew_user)(
                    agency=agent_obj.agency,
                    agentuser=request.user,
                    plan=renewuser_form.cleaned_data["plan"],
                    plan_args=renewuser_form.get_plan_args(),
                    profile=selected_user,
                )
                return redirect(request.get_full_path())
            errors.update(**renewuser_form.errors)
        else:
            renewuser_form = forms.RenewUserForm(profile=selected_user, current_period=selected_user.current_period, prefix="newuser1")
        # end

        creatable_plans_qs = renewuser_form.fields["plan"].queryset
        normal_sublink = await sync_to_async(selected_user.get_sublink)()
        b64_sublink = normal_sublink + "?base64=true"
        if request.GET and request.POST.get("action") == "suspend":
            await sync_to_async(services.suspend_user)(selected_user, agentuser=request.user)
            return redirect(request.get_full_path())
        elif request.GET and request.POST.get("action") == "unsuspend":
            await sync_to_async(services.unsuspend_user)(selected_user, agentuser=request.user)
            return redirect(request.get_full_path())

    return {
        "current_agency_id": current_agency_id,
        "agencies": [{"id": i.agency.id, "name": i.agency.name} for i in agent_accounts],
        "creatable_plans": [
            {
                "id": str(i.id),
                "name": i.name,
                "plan_provider_key": i.plan_provider_key,
                "plan_provider_args": i.plan_provider_args,
            }
            async for i in creatable_plans_qs
        ],
        "logout_url": reverse("BabyUI:logout"),
        "users_list_page": users_res.model_dump(),
        "selected_user": {
            "title": selected_user.title,
            "created_at_str": jformat(selected_user.created_at.astimezone(ZoneInfo("Asia/Tehran")), "%Y/%m/%d %H:%M"),
            "is_suspended": not selected_user.is_active,
            "plan": {
                "id": str(selected_user.current_period.plan.id),
                "name": selected_user.current_period.plan.name,
                "plan_provider_key": selected_user.current_period.plan.plan_provider_key,
                "plan_provider_args": selected_user.current_period.plan.plan_provider_args,
            },
            "sublink": {"normal": normal_sublink, "b64": b64_sublink},
            "events": [
                {
                    "id": str(i.id),
                    "title": i.title,
                    "created_at_str": jformat(i.created_at.astimezone(ZoneInfo("Asia/Tehran")), "%Y/%m/%d %H:%M"),
                }
                async for i in user_events
            ],
            "periods_list_page": periods_res.model_dump(),
        }
        if selected_user
        else None,
        "errors": errors,
    }
