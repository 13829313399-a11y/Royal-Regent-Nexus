"""Small, explicit Python 3.8 backports for the offline Windows 7 build only."""
import asyncio
import builtins
import contextvars
import functools
import itertools
import operator


def union(left, right):
    if type(left) is dict and type(right) is dict:
        result = left.copy()
        result.update(right)
        return result
    return operator.or_(left, right)


def zip_compat(*iterables, strict=False):
    if not strict:
        return builtins.zip(*iterables)
    def checked():
        sentinel = object()
        for values in itertools.zip_longest(*iterables, fillvalue=sentinel):
            if any(value is sentinel for value in values):
                raise ValueError('zip() arguments have different lengths')
            yield values
    return checked()


def removeprefix(value, prefix):
    return value[len(prefix):] if value.startswith(prefix) else value


def removesuffix(value, suffix):
    return value[:-len(suffix)] if suffix and value.endswith(suffix) else value


async def to_thread(function, *args, **kwargs):
    context = contextvars.copy_context()
    return await asyncio.get_running_loop().run_in_executor(
        None, functools.partial(context.run, function, *args, **kwargs))


def flattened_data(image):
    # Pillow 12 renamed the old ImagingCore API; retain the same ordered pixels.
    return list(image.getdata())
