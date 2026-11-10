"""Explicit private real-document regression. No database or production writes."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings
from app.services.document_tools.image_translation import convert_image_translation
from app.services.document_tools.translation_engine import convert_translation
from app.services.document_tools.document_ir import ToolError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--engine", choices=["online", "offline"], default="online")
    parser.add_argument("--operation",choices=["image_translate","pdf_translate"],default="image_translate")
    parser.add_argument('--fresh-reading',action='store_true')
    args = parser.parse_args()
    cases = json.loads(args.manifest.read_text(encoding="utf-8"))
    if isinstance(cases, dict):
        cases = cases["cases"]
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / ".gitignore").write_text("*\n", encoding="utf-8")
    results = []
    for index, case in enumerate(cases):
        source = Path(case["path"]).resolve()
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        work = args.output / f"case-{index+1:02d}"
        started = time.monotonic()
        def progress(stage, completed, total):
            print(json.dumps({"case":case["name"],"stage":stage,"completed":completed,"total":total,
                              "seconds":round(time.monotonic()-started,1)},ensure_ascii=False), flush=True)
        try:
            options={
                "translation_engine":args.engine, "translation_direction":case.get("direction", "en_to_zh"),
                "page_selection":case.get("pages", "all"), "glossary":case.get("glossary", ""),'refresh_source':args.fresh_reading}
            converted = (convert_translation(source,args.operation,options,work,progress,lambda:False)
                if args.operation=='pdf_translate' else convert_image_translation(source,options,work,progress,lambda:False))
            document_pages=list(converted.ir.engine_manifest.get('document_pages',{}).values())
            calls=[c for p in document_pages for c in p.get('calls',[])]
            report = {"name":case["name"],"passed_execution":True,"source":str(source),"selection":case.get("pages", "all"),
                "summary":converted.summary,"issues":[issue.model_dump() for issue in converted.ir.issues],
                "model":settings.document_tools_translation_model if args.engine=="online" else "offline", "operation":args.operation,
                'actual_models':sorted({c.get('model','') for c in calls if not c.get('cache_hit')}),
                'source_cache_hits':sum(bool(p.get('evidence',{}).get('source_cache_hit')) for p in document_pages),
                'source_fallback_pages':sum(bool(p.get('evidence',{}).get('source',{}).get('source_fallback')) for p in document_pages),
                'rejected_source_responses':sum(len(p.get('evidence',{}).get('source',{}).get('rejected_responses',[])) for p in document_pages),
                'provider_calls':len([c for c in calls if not c.get('cache_hit')]),
                "files":[{"role":item["role"],"path":str(item["path"])} for item in converted.files]}
            (work / "result-ir.json").write_text(json.dumps(converted.ir.model_dump(mode="json"),ensure_ascii=False,indent=2),encoding="utf-8")
        except ToolError as error:
            report = {"name":case["name"],"passed_execution":False,"error_code":error.code,"error":error.message}
        except Exception as error:
            report = {"name":case["name"],"passed_execution":False,"error_type":type(error).__name__}
        report.update(seconds=round(time.monotonic()-started,2),source_sha256=digest,
                      source_unchanged=hashlib.sha256(source.read_bytes()).hexdigest()==digest)
        results.append(report)
        (args.output / "results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({"case":case["name"],"done":True,"passed_execution":report["passed_execution"],
                          "summary":report.get("summary"),"error":report.get("error"),"seconds":report["seconds"]},ensure_ascii=False),flush=True)
    # Execution success is deliberately distinct from semantic/visual acceptance.
    if not all(result["passed_execution"] and result["source_unchanged"] for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
