from asgiref.sync import sync_to_async

from django.http import HttpResponse


async def nginx_flower_auth_request(request):
    is_authenticated = await sync_to_async(lambda: request.user.is_authenticated)()
    if not is_authenticated:
        return HttpResponse(status=401)
    if not request.user.is_superuser:
        return HttpResponse(status=403)
    return HttpResponse(status=200)

async def tmp_rz1(request):
    import django.shortcuts
    import random
    import pydantic
    from functools import partial
    from django.utils import timezone
    from zoneinfo import ZoneInfo
    from django.http import HttpResponse
    import io
    import csv

    if request.GET.get("csv"):
        class TMP_RZ1(pydantic.BaseModel):
            contract_name: str = pydantic.Field(serialization_alias='قرارداد (فیک)')
            profit_percent: int = pydantic.Field(serialization_alias='سود ثابت (فیک)')
            last_update_at: pydantic.AwareDatetime = pydantic.Field(serialization_alias='زمان آخرین بروز رسانی')

        res = []
        contracts = ["بیبی", "بیبیب", "بیبیب", "لبلب", "قثفق", "لبلبل"]
        for i in range(6):
            res.append(
                TMP_RZ1(contract_name=contracts[i], profit_percent=random.randint(10, 100),
                        last_update_at=str(timezone.now()))
            )
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=res[0].dict(by_alias=True).keys())
        writer.writeheader()
        for r in res:
            writer.writerow(r.dict(by_alias=True))

        # Move cursor to the beginning of the buffer
        buffer.seek(0)

        response = HttpResponse(buffer, content_type="text/csv")
        return response

    return django.shortcuts.render(
        request, "core/tmp_rz1.html", {
            "random_int": partial(random.randint, 1, 100),
            "last_update_at": timezone.localtime(timezone=ZoneInfo("Asia/Tehran"))
        }
    )
