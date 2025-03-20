from inertia import inertia

from django.shortcuts import render


def aaa(request):
    return render(request, "BabyUI/aaa.html", {})


@inertia("Home/Index")
def index(request):
    return {}
