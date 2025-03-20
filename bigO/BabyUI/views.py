from bigO.utils.inertia import inertia
from django.shortcuts import render


def aaa(request):
    return render(request, "BabyUI/aaa.html", {})


@inertia("Home/Index", layout="BabyUI/page.html")
def index(request):
    return {"title": f"hello {request.user.username}"}


@inertia("Home/Dashboard", layout="BabyUI/page.html")
def dashboard(request):
    return {}
