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
    import csv
    import io
    import random
    from decimal import ROUND_HALF_UP, Decimal
    from functools import partial
    from zoneinfo import ZoneInfo

    import influxdb_client
    import pandas as pd
    import pydantic

    import django.shortcuts
    from config import settings
    from django.http import HttpResponse
    from django.utils import timezone

    if request.GET.get("csv"):

        class TMP_RZ1(pydantic.BaseModel):
            contract_name: str = pydantic.Field(serialization_alias="قرارداد")
            profit_percent: Decimal | None = pydantic.Field(serialization_alias="سود ثابت")
            last_update_at: pydantic.AwareDatetime | None = pydantic.Field(serialization_alias="زمان آخرین بروز رسانی")

        bucket = settings.env.str("rz_bucket")
        org = settings.env.str("rz_org")
        token = settings.env.str("rz_token")
        url = settings.env.str("rz_url")
        query = f"""
        from(bucket: "{bucket}")
        |> range(start: -10m)
        |> filter(fn: (r) => r["_measurement"] == "ahrom")
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        """
        df = influxdb_client.InfluxDBClient(url=url, token=token, org=org).query_api().query_data_frame(query=query)
        df["_time"] = pd.to_datetime(df["_time"])
        df_sorted = df.sort_values(by=["contrace_number", "_time"], ascending=[True, False])
        latest_df = df_sorted.drop_duplicates(subset="contrace_number", keep="first")
        latest_df = latest_df.sort_values(by="_time", ascending=False)

        res = []
        contracts = ["0119", "0120", "0121", "0122", "0123", "0124", "2015", "2016", "2017", "2018", "2019"]
        for i in contracts:
            contract_info = latest_df[latest_df["contrace_number"] == i]
            if contract_info.empty:
                res.append(TMP_RZ1(contract_name=i, profit_percent=None, last_update_at=None))
            else:
                record = contract_info.iloc[0].to_dict()
                res.append(
                    TMP_RZ1(
                        contract_name=i,
                        profit_percent=Decimal(record["calc3"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                        last_update_at=str(record["_time"]),
                    )
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
        request,
        "core/tmp_rz1.html",
        {
            "random_int": partial(random.randint, 1, 100),
            "last_update_at": timezone.localtime(timezone=ZoneInfo("Asia/Tehran")),
        },
    )
