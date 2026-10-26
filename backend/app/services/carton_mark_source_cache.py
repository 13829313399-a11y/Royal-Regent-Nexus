"""Bounded memory caches for immutable facts from caller-supplied source bytes.

Authorization and source revision checks remain outside and precede these caches.
No account/order identity, tokens or provider response is cached here.
"""
import copy
import hashlib
import threading
import time
from collections import OrderedDict

_LOCK=threading.Lock()
_NATIVE=OrderedDict()
_FLOW=OrderedDict()


def memo(cache,key,build,limit):
    with _LOCK:
        found=cache.get(key)
        if found and time.monotonic()-found[0]<3600:
            cache.move_to_end(key);return copy.deepcopy(found[1])
    result=build()
    with _LOCK:
        cache[key]=(time.monotonic(),copy.deepcopy(result))
        while len(cache)>limit:cache.popitem(last=False)
    return result


def document(filename,content):
    from app.services.carton_mark import extract_excel_document_items
    key=(filename.rsplit('.',1)[-1].lower(),hashlib.sha256(content).digest())
    return memo(_NATIVE,key,lambda:extract_excel_document_items(filename,content),8)


def source(filename,content,worksheets=None):
    from app.services import carton_mark_flexible as flow
    key=(filename.rsplit('.',1)[-1].lower(),hashlib.sha256(content).digest(),tuple(worksheets or []))
    return memo(_FLOW,key,lambda:flow.read(filename,content,allow_unresolved=True,worksheets=worksheets,
                                         extracted=document(filename,content)),32)
