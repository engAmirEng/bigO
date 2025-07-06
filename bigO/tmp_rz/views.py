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
from django.db.models import Prefetch
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.utils import timezone
from . import settings, models
import simpleeval


async def tmp_rz1(request):
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
        type1_configs = models.Type1Config.objects.select_related("ahrom").order_by("order")
        contracts = [i.ahrom.contract_num async for i in type1_configs]
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
        "tmp_rz/tmp_rz1.html",
        {
            "random_int": partial(random.randint, 1, 100),
            "last_update_at": timezone.localtime(timezone=ZoneInfo("Asia/Tehran")),
        },
    )

async def tmp_rz2(request):
    config = await models.Config.objects.aget()
    if not config.type2_formula:
        raise PermissionDenied("config.type2_formula is empty")
    expressions_var = config.get_type2_expressions_var()
    parsed_expressions = []
    s = simpleeval.SimpleEval()
    for var_name, expression in expressions_var:
        parsed_expressions.append(s.parse(expression))

    if request.GET.get("csv"):
        class TMP_RZ2(pydantic.BaseModel):
            title: str = pydantic.Field(serialization_alias="عنوان")
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
        async for type2 in models.Type2Config.objects\
            .select_related("foroosh_ahrom")\
            .prefetch_related(
                Prefetch(
                    "relates",
                    queryset=models.Type2Relate.objects.select_related("kharid_ahrom").order_by("order"),
                    to_attr="all_relates"
                )
            )\
            .order_by("order"):
            foroosh_contract_info = latest_df[latest_df["contrace_number"] == type2.foroosh_ahrom.contract_num]
            for type2_relate in type2.all_relates:
                kharid_contract_info = latest_df[latest_df["contrace_number"] == type2_relate.kharid_ahrom.contract_num]
                if foroosh_contract_info.empty:
                    res.append(TMP_RZ2(contract_name=type2.main_ahrom.contract_num, profit_percent=None, last_update_at=None))
                elif kharid_contract_info.empty:
                    res.append(TMP_RZ2(contract_name=type2.main_ahrom.contract_num, profit_percent=None, last_update_at=None))
                else:
                    foroosh_record = foroosh_contract_info.iloc[0].to_dict()
                    kharid_record = kharid_contract_info.iloc[0].to_dict()
                    assert foroosh_record["ahrom_last_price"] == kharid_record["ahrom_last_price"]
                    ahrom_last_price = foroosh_record["ahrom_last_price"]
                    s.names = simpleeval.DEFAULT_NAMES
                    for i, pe in enumerate(parsed_expressions):
                        s.names.update({"foroosh_record": foroosh_record, "kharid_record": kharid_record, "ahrom_last_price": ahrom_last_price})
                        expression_var = expressions_var[i]
                        r = s.eval(expression_var[1], previously_parsed=pe)
                        s.names.update({expression_var[0]: r})
                    bazdeh = s.names["bazdeh"]
                    risk_percentage = s.names["risk_percentage"]
                    res.append(
                        TMP_RZ2(
                            title=type2.title or "",
                            foroosh_contract_name=type2.foroosh_ahrom.contract_num,
                            kharid_contract_name=type2_relate.kharid_ahrom.contract_num,
                            bazdeh=Decimal(bazdeh).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                            risk_percentage=Decimal(risk_percentage).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                            last_update_at=str(max(foroosh_record["_time"], kharid_record["_time"])),
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
        "tmp_rz/tmp_rz1.html",
        {
            "random_int": partial(random.randint, 1, 100),
            "last_update_at": timezone.localtime(timezone=ZoneInfo("Asia/Tehran")),
        },
    )
