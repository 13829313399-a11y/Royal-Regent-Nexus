"""Bounded lexical retrieval. Callers supply only current, authorized snapshots."""
from collections import Counter
import hashlib
import json
import math
import re
import unicodedata

CHUNK_SIZE = 1000
OVERLAP = 128
MAX_HITS = 12
TOKEN = re.compile(r'[a-z0-9]+(?:[-_./][a-z0-9]+)*|[\u3400-\u9fff]+')
STOP = {'the','and','for','with','this','that','from','what','please','read','find','show',
        '读取','查找','查询','请问','文件','资料','文档','内容','中的','什么','如何','这个','请查'}


def normalized(text):
    return unicodedata.normalize('NFKC', text).casefold()


def tokens(text):
    result = []
    for token in TOKEN.findall(normalized(text)):
        if re.search(r'[\u3400-\u9fff]', token):
            pieces = [token] if len(token) <= 6 else []
            pieces += [token[i:i+2] for i in range(len(token)-1)]
        else:
            pieces = [token] + re.split(r'[-_./]', token) if re.search(r'[-_./]', token) else [token]
        result.extend(piece for piece in pieces if piece and piece not in STOP)
    return result


def identifiers(query):
    # Pure short numbers are usually page/paragraph positions; preserve leading
    # zero identifiers and complete mixed alphanumeric identifiers exactly.
    query = re.sub(r'(?:第\s*)?\d+\s*[页段]|(?:page|paragraph)\s+\d+', ' ', normalized(query))
    return tuple(dict.fromkeys(t for t in TOKEN.findall(query)
        if not re.search(r'[\u3400-\u9fff]', t) and
        ((re.search('[a-z]', t) and re.search('[0-9]', t)) or
         (t.isdigit() and (len(t) >= 3 or (len(t) > 1 and t.startswith('0')))))))


def exact(text, term):
    return bool(re.search(r'(?<![a-z0-9_./-])'+re.escape(term)+r'(?![a-z0-9_./-])', normalized(text)))


def spans(text):
    if len(text) <= CHUNK_SIZE:
        yield 0, len(text)
        return
    start = 0
    while start < len(text):
        end = min(len(text), start + CHUNK_SIZE)
        if end < len(text):
            boundary = text.rfind('\n', start + CHUNK_SIZE//2, end)
            if boundary >= 0:
                end = boundary + 1
        yield start, end
        if end == len(text):
            break
        start = end - OVERLAP


def location_match(query, locator):
    pages = [int(value) for pair in re.findall(r'(?:第\s*)?(\d+)\s*页|page\s+(\d+)', normalized(query)) for value in pair if value]
    paragraphs = [int(value) for pair in re.findall(r'(?:第\s*)?(\d+)\s*段|paragraph\s+(\d+)', normalized(query)) for value in pair if value]
    cells = set(re.findall(r'(?<![a-z0-9])([a-z]{1,3}[1-9][0-9]{0,6})(?![a-z0-9])', normalized(query)))
    if locator['kind'] in ('page','ocr_region') and locator['page'] in pages:
        return True
    if locator['kind'] == 'paragraph' and locator['paragraph'] in paragraphs:
        return True
    if locator['kind'] == 'sheet' and locator['cells'].casefold() in cells:
        return True
    return False


def chunk_records(documents):
    records = []
    for document in documents:
        chunk_index = 0
        for index, segment in enumerate(document['segments']):
            fingerprint = segment_hash(segment)
            for start, end in spans(segment['text']):
                text = segment['text'][start:end]
                metadata = segment.get('metadata', {})
                searchable = text + '\n' + json.dumps(segment['locator'], ensure_ascii=False) + '\n' + str(metadata.get('heading') or '') + '\n' + document['name']
                records.append(dict(file_id=document['id'], name=document['name'], document_version=document['version'],
                    segment_index=index, document_chunk_index=chunk_index, text=text, locator=segment['locator'], metadata=metadata,
                    excerpt_range=dict(start=start,end=end,total=len(segment['text'])),
                    segment_hash=fingerprint, chunk_hash=hashlib.sha256(text.encode()).hexdigest(),
                    terms=Counter(tokens(searchable)), searchable=searchable))
                chunk_index += 1
    return records


def segment_hash(segment):
    # Version envelopes do not change the hash of the original locator/text.
    return hashlib.sha256(json.dumps({k:v for k,v in segment.items() if k not in ('document_version','original_hash')},
                                    ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def version_segments(original_hash, segments):
    index_hash = hashlib.sha256(json.dumps([
        {k:v for k,v in segment.items() if k not in ('document_version','original_hash')}
        for segment in segments],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return hashlib.sha256((original_hash+':'+index_hash).encode()).hexdigest()


def stamp_segments(raw, segments):
    original_hash = hashlib.sha256(raw).hexdigest()
    version = version_segments(original_hash,segments)
    return [dict(**segment,original_hash=original_hash,document_version=version) for segment in segments]


def retrieve(documents, query, character_budget, max_hits=MAX_HITS):
    """Return selected chunks plus truthful coverage; never insert a full corpus."""
    terms = set(tokens(query))
    ids = identifiers(query)
    if len(terms) > 256 or len(ids) > 32:
        raise ValueError('retrieval_query_limit')
    records = chunk_records(documents)
    overview = not query.strip() or bool(re.search(r'总结|概括|主要发现|分析这些文件|整理.*(?:文件|资料)|overview|summary', normalized(query)))
    counts = Counter(t for record in records for t in record['terms'])
    avg_length = sum(sum(r['terms'].values()) for r in records)/max(1,len(records))
    any_location = any(location_match(query, r['locator']) for r in records)
    location_requested = bool(re.search(r'(?:\d+\s*[页段]|(?:page|paragraph)\s+\d+)', normalized(query)))
    matched_ids = set()
    ranked = []
    for ordinal, record in enumerate(records):
        matches = [term for term in ids if exact(record['searchable'],term)]
        matched_ids.update(matches)
        position = location_match(query,record['locator'])
        score = 0.
        for term in terms:
            freq = record['terms'][term]
            if freq:
                length = sum(record['terms'].values())
                idf = math.log(1+(len(records)-counts[term]+.5)/(counts[term]+.5))
                score += idf * freq * 2.2/(freq+1.2*(.25+.75*length/max(1,avg_length)))
        # Explicit identifiers/locations cannot silently fall back to a similar
        # identifier or an unrelated keyword hit when the exact value is absent.
        if ids or any_location or location_requested:
            if not matches and not position:
                continue
            rank = (2 if matches or position else 0, len(matches), score, -ordinal)
            reason = 'exact_identifier' if matches else 'explicit_location'
        elif overview:
            # Round-robin across documents before deeper excerpts, so a small
            # context does not silently claim to summarize only the first file.
            rank = (0,0,-record['document_chunk_index'],-ordinal); reason='overview_sample'
        elif score > 0:
            rank = (1,0,score,-ordinal); reason='keyword'
        else:
            continue
        ranked.append((rank,record,reason))
    ranked.sort(key=lambda value:value[0],reverse=True)
    selected, used = [], 0
    for _, record, reason in ranked:
        if len(selected) >= max(1,min(MAX_HITS,max_hits)):
            break
        public = {k:v for k,v in record.items() if k not in ('terms','searchable')}
        public['match_reason'] = reason
        public['matched_identifiers'] = [term for term in ids if exact(record['searchable'],term)]
        size = len(json.dumps(public,ensure_ascii=False,separators=(',',':')))
        if used + size > character_budget:
            continue
        # Avoid sending overlapping pieces from the same segment twice unless
        # they contain distinct exact identifiers requested in this question.
        if any(p['file_id']==record['file_id'] and p['segment_index']==record['segment_index'] and
               max(p['excerpt_range']['start'],record['excerpt_range']['start']) <
               min(p['excerpt_range']['end'],record['excerpt_range']['end']) for p in selected) and not (
                   set(public['matched_identifiers']) - {term for p in selected for term in p['matched_identifiers']}):
            continue
        selected.append(public); used += size
    report = dict(strategy='exact_location_then_lexical_v1', query_hash=hashlib.sha256(query.encode()).hexdigest(),
                  total_chunks=len(records), matched_chunks=len(ranked), selected_chunks=len(selected),
                  selected_characters=used, character_budget=character_budget,
                  coverage='complete' if selected and len(selected)==len(records) else 'partial' if selected else 'no_match',
                  unmatched_identifiers=[term for term in ids if term not in matched_ids],
                  versions={d['id']:d['version'] for d in documents},
                  notice='仅所列片段进入本轮上下文；未召回不代表文档不存在该事实。')
    report['documents'] = {d['id']:dict(
        total_chunks=sum(r['file_id']==d['id'] for r in records),
        matched_chunks=sum(r['file_id']==d['id'] for _,r,_ in ranked),
        selected_chunks=sum(r['file_id']==d['id'] for r in selected)) for d in documents}
    if ranked and not selected:
        report['coverage']='budget_exhausted'
    return selected, report
