from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from bigO.utils.inertia import inertia
from django.shortcuts import render


def aaa(request):
    return render(request, "BabyUI/aaa.html", {})

@inertia("Auth/SignIn", layout="BabyUI/page.html")
async def signin(request):
    return {}

@login_required(login_url=reverse_lazy("BabyUI:signin"))
@inertia("Home/Index", layout="BabyUI/page.html")
async def index(request):
    user = await request.auser()
    return {"title": f"hello {user.username}"}


@inertia("Home/Dashboard", layout="BabyUI/page.html")
def dashboard(request):
    return {}
