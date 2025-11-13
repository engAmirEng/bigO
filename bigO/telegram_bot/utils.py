from typing import TypedDict
from django.utils.translation import get_language
from asgiref.sync import async_to_sync, sync_to_async

from aiogram.fsm.context import FSMContext
from django.contrib import messages
from django.template.loader import render_to_string


async def thtml_render_to_string(template_name, context=None, request=None, using=None):
    rendered = await sync_to_async(render_to_string)(template_name, context=context, request=request, using=using)
    # digit translation
    english = "0123456789"
    farsi = "۰۱۲۳۴۵۶۷۸۹"
    language = get_language()
    if language == "fa":
        rendered = rendered.translate(str.maketrans(english, farsi))
    # # # # #
    lines = rendered.replace("\n", "").split("<br>")
    result_lines = []
    for line in lines:
        line: str
        result_lines.append(line.lstrip().rstrip().replace("&nbsp;", " "))
    return "\n".join(result_lines)


class TMessage(TypedDict):
    level: int
    message: str


async def add_message(state: FSMContext, level, message):
    data = await state.get_data()
    messages: list[TMessage] = data.get("messages", [])
    messages.append({"level": level, "message": message})
    data["messages"] = messages
    await state.set_data(data=data)


async def get_message(state: FSMContext, preserve=False):
    data = await state.get_data()
    messages: list[TMessage] = data.get("messages", [])
    if not preserve:
        data["messages"] = []
        await state.set_data(data=data)
    return messages
