"""Bounded process-local snapshots; callers must authorize every cache hit."""
from collections import OrderedDict
from copy import deepcopy
import json
import re
import threading
import time


STRICT_CURRENT=re.compile(r'当前|现在|今天|今日|刷新|最新|实时|还剩|剩余|待处理|重新|更新|相比|比较|对比|比对|变化|变动|上次|之前|先前|再次|\b(?:now|current|today|refresh|latest|remaining|compare|changes?|again|real[ -]?time)\b',re.I)


def allowed_for(payload):
    return payload.intent=='chat' and payload.relation is None and not payload.context_selection and not STRICT_CURRENT.search(payload.text)


class RecentReads:
    def __init__(self,*,entries=128,bytes_limit=8*1024*1024,owner_entries=16,owner_bytes=1024*1024,clock=None):
        if min(entries,bytes_limit,owner_entries,owner_bytes)<1:raise ValueError('Cache bounds must be positive')
        self.entries=entries;self.bytes_limit=bytes_limit
        self.owner_entries=owner_entries;self.owner_bytes=owner_bytes
        self.clock=clock or time.monotonic
        self._items=OrderedDict();self._lock=threading.Lock()

    def _expire(self):
        now=self.clock()
        for key in list(self._items):
            if self._items[key]['deadline']<=now:del self._items[key]

    def get(self,key):
        with self._lock:
            self._expire()
            entry=self._items.get(key)
            if entry is None:return None
            self._items.move_to_end(key)
            return deepcopy(entry['value'])

    def discard(self,key):
        with self._lock:self._items.pop(key,None)

    def retain_scope(self,owner,fingerprint):
        with self._lock:
            self._expire()
            for key in list(self._items):
                if key[0]==owner and key[1]!=fingerprint:del self._items[key]

    def clear_owner(self,owner):
        with self._lock:
            for key in list(self._items):
                if key[0]==owner:del self._items[key]

    def put(self,key,value,*,ttl=30):
        # All values are already validated, bounded JSON domain projections.
        encoded=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()
        size=len(encoded);owner=key[0]
        with self._lock:
            self._expire();self._items.pop(key,None)
            if size>min(self.bytes_limit,self.owner_bytes) or ttl<=0:return False
            same=lambda:[k for k,v in self._items.items() if k[0]==owner]
            while len(same())>=self.owner_entries or sum(self._items[k]['bytes'] for k in same())+size>self.owner_bytes:
                del self._items[same()[0]]
            while len(self._items)>=self.entries or sum(v['bytes'] for v in self._items.values())+size>self.bytes_limit:
                self._items.popitem(last=False)
            self._items[key]=dict(value=deepcopy(value),bytes=size,deadline=self.clock()+min(ttl,30))
            return True
