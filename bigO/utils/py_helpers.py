def access_index_default(iterable: iter, index: int, default):
    try:
        value = iterable[index]
    except IndexError:
        value = default
    return value
