from typing import TypedDict

from asgiref.sync import async_to_sync, sync_to_async

from aiogram.fsm.context import FSMContext
from django.contrib import messages
from django.template.loader import render_to_string
from django.utils.translation import get_language


async def thtml_render_to_string(template_name, context=None, request=None, using=None):
    rendered = await sync_to_async(render_to_string)(template_name, context=context, request=request, using=using)
    lines_list = []
    for line in rendered.split("\n"):
        lines_list.append(line.lstrip().rstrip())
    result_lines_list = []
    for line in "".join(lines_list).split("<br>"):
        result_lines_list.append(line.lstrip().rstrip().replace("&nbsp;", " "))
    return "\n".join(result_lines_list)


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
