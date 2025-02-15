from django.http import HttpResponse


def nginx_flower_auth_request(request):
    if not request.user.is_authenticated:
        return HttpResponse(status=401)
    if not request.user.is_superuser:
        return HttpResponse(status=403)
    return HttpResponse(status=200)
