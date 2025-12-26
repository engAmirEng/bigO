from typing import TypedDict

from asgiref.sync import sync_to_async

from aiogram.fsm.context import FSMContext
from django.template.loader import render_to_string


def thtml_normalize_markup(rendered_content: str):
    lines_list = []
    for line in rendered_content.split("\n"):
        lines_list.append(line.lstrip().rstrip())
    result_lines_list = []
    for line in "".join(lines_list).split("<br>"):
        result_lines_list.append(line.lstrip().rstrip().replace("&nbsp;", " "))
    return "\n".join(result_lines_list)


def thtml_reverse_normalize_markup(normalized_html_content: str):
    lines_list = []
    for line in normalized_html_content.split("\n"):
        lines_list.append(line.lstrip().rstrip())
    result_lines_list = []
    for line in lines_list:
        new_line = line
        if line.startswith(" "):
            prefix = ""
            for char in line:
                if char != " ":
                    break
                prefix += "&nbsp;"
            new_line = prefix + line.lstrip()
        result_lines_list.append(new_line)
    return "\n<br>".join(result_lines_list)


async def thtml_render_to_string(template_name, context=None, request=None, using=None):
    rendered = await sync_to_async(render_to_string)(template_name, context=context, request=request, using=using)
    return thtml_normalize_markup(rendered_content=rendered)


def sync_thtml_render_to_string(template_name, context=None, request=None, using=None):
    rendered = render_to_string(template_name, context=context, request=request, using=using)
    return thtml_normalize_markup(rendered_content=rendered)


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
