async def wrap_awaitable(awaitable_instance):
    """
    A handy shortcut when dealing with objects that implement __await__
    and you want to do something like:
        ```
            class A:
                def __await__(self):
                    ...
            asyncio.create_task(A()) does not work
            asyncio.create_task(wrap_awaitable(A())) work
        ```
    """
    return await awaitable_instance
