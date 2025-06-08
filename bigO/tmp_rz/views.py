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
from django.http import HttpResponse
from django.utils import timezone
from . import settings, models


async def tmp_rz1(request):
    if request.GET.get("csv"):

        class TMP_RZ2(pydantic.BaseModel):
            foroosh_contract_name: str = pydantic.Field(serialization_alias="قرارداد طهرم")
            kharid_contract_name: str = pydantic.Field(serialization_alias="قرارداد ضهرم")
            bazdeh: Decimal | None = pydantic.Field(serialization_alias="بازده")
            risk_percentage: Decimal | None = pydantic.Field(serialization_alias="درصد ریسک")
            last_update_at: pydantic.AwareDatetime | None = pydantic.Field(serialization_alias="زمان آخرین بروز رسانی")

        query = f"""
        from(bucket: "{settings.bucket}")
        |> range(start: -10m)
        |> filter(fn: (r) => r["_measurement"] == "ahrom")
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        """
        df = influxdb_client.InfluxDBClient(url=settings.url, token=settings.token, org=settings.org).query_api().query_data_frame(query=query)
        df["_time"] = pd.to_datetime(df["_time"])
        df_sorted = df.sort_values(by=["contrace_number", "_time"], ascending=[True, False])
        latest_df = df_sorted.drop_duplicates(subset="contrace_number", keep="first")
        latest_df = latest_df.sort_values(by="_time", ascending=False)

        res = []
        for type2 in models.Type2Config.objects.all().select_related("main_ahrom").order_by("order"):
            foroosh_contract_info = latest_df[latest_df["contrace_number"] == type2.foroosh_ahrom.contract_num]
            for i in type2.items:
                kharid_contract_info = latest_df[latest_df["contrace_number"] == i.kharid_ahrom.contract_num]
                if foroosh_contract_info.empty:
                    res.append(TMP_RZ2(contract_name=type2.main_ahrom.contract_num, profit_percent=None, last_update_at=None))
                elif kharid_contract_info.empty:
                    res.append(TMP_RZ2(contract_name=type2.main_ahrom.contract_num, profit_percent=None, last_update_at=None))
                else:
                    foroosh_record = foroosh_contract_info.iloc[0].to_dict()
                    khalid_record = kharid_contract_info.iloc[0].to_dict()
                    res.append(
                        TMP_RZ2(
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

        response = HttpResponse(buffer, content_type="text/csv", headers={"Content-Disposition": "inline;"})
        return response

    return django.shortcuts.render(
        request,
        "tmp_rz/tmp_rz1.html",
        {
            "random_int": partial(random.randint, 1, 100),
            "last_update_at": timezone.localtime(timezone=ZoneInfo("Asia/Tehran")),
        },
    )

async def tmp_rz2(request):
    if request.GET.get("csv"):
        class TMP_RZ1(pydantic.BaseModel):
            contract_name: str = pydantic.Field(serialization_alias="قرارداد")
            profit_percent: Decimal | None = pydantic.Field(serialization_alias="سود ثابت")
            last_update_at: pydantic.AwareDatetime | None = pydantic.Field(serialization_alias="زمان آخرین بروز رسانی")

        query = f"""
        from(bucket: "{settings.bucket}")
        |> range(start: -10m)
        |> filter(fn: (r) => r["_measurement"] == "ahrom")
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        """
        df = influxdb_client.InfluxDBClient(url=settings.url, token=settings.token, org=settings.org).query_api().query_data_frame(query=query)
        df["_time"] = pd.to_datetime(df["_time"])
        df_sorted = df.sort_values(by=["contrace_number", "_time"], ascending=[True, False])
        latest_df = df_sorted.drop_duplicates(subset="contrace_number", keep="first")
        latest_df = latest_df.sort_values(by="_time", ascending=False)

        res = []
        contracts = [
            "0119",
            "0120",
            "0121",
            "0122",
            "0123",
            "0124",
            "2015",
            "2016",
            "2017",
            "2018",
            "2019",
            "3014",
            "3015",
            "3016",
            "3017",
            "3018",
            "3019",
            "3020",
            "3021",
            "4016",
            "4017",
            "4018",
            "4019",
            "4020",
            "4021",
            "4022",
        ]
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

        response = HttpResponse(buffer, content_type="text/csv", headers={"Content-Disposition": "inline;"})
        return response
