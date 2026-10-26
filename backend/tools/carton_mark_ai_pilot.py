"""Run the isolated first template; never writes business records.

python backend/tools/carton_mark_ai_pilot.py --excel FILE --reference FILE
    --env-file .local-dev/carton-ai-pilot.env --output output/pdf/zumiez-ai-pilot.pdf
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.carton_mark_ai_pilot import (PilotError,load_template,collect_evidence,
    connection_from_file,request_plan,validate_plan,render_review)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--excel",type=Path,required=True)
    parser.add_argument("--reference",type=Path,required=True)
    parser.add_argument("--env-file",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--template",type=Path)
    parser.add_argument("--reuse-response",type=Path,help="Replay an exact source/template-bound saved model response without another paid call")
    args=parser.parse_args()
    template=load_template(args.template) if args.template else load_template()
    evidence,native,hashes=collect_evidence(args.excel,args.reference)
    if hashes["reference_sha256"]!=template["reference_sha256"]:
        raise PilotError("本模板与参考PDF不匹配")
    fingerprint={**hashes,"template_sha256":hashlib.sha256(json.dumps(template,sort_keys=True).encode()).hexdigest()}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.reuse_response:
        saved=json.loads(args.reuse_response.read_text(encoding="utf-8"))
        if saved["input_fingerprint"]!=fingerprint:
            raise PilotError("已保存响应与本次原稿或模板不匹配")
        raw,receipt=saved["raw"],saved["provider"]
    else:
        if not args.env_file:
            raise PilotError("真实模型调用需要私有连接配置")
        raw,receipt=request_plan(evidence,template,connection_from_file(args.env_file))
        args.output.with_suffix(".response.json").write_text(json.dumps({"input_fingerprint":fingerprint,
            "raw":raw,"provider":receipt},ensure_ascii=False,indent=2),encoding="utf-8")
    plan,values,provenance=validate_plan(raw,evidence,template,native)
    content,layout=render_review(args.reference.read_bytes(),template,values,provenance,api_verified=True,
                                 layout_variant=plan.layout_variant)
    if (hashlib.sha256(args.excel.read_bytes()).hexdigest()!=hashes["excel_sha256"] or
            hashlib.sha256(args.reference.read_bytes()).hexdigest()!=hashes["reference_sha256"]):
        raise PilotError("渲染期间原稿发生变化，结果未发布")
    args.output.write_bytes(content)
    report={"status":"api_verified_review_only","template_id":template["id"],"plan":plan.model_dump(),
            "provider":receipt,"sources":{"excel":args.excel.name,"reference":args.reference.name,**hashes},
            "fields":provenance,"layout":layout,"output_sha256":hashlib.sha256(content).hexdigest(),
            "business_data_written":False,"production_print_approved":False}
    args.output.with_suffix(".receipt.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"status":report["status"],"output":str(args.output.resolve()),"model":receipt["returned_model"],
                      "pages":layout["pages"],"source_integrity":"unchanged"},ensure_ascii=True))


if __name__=="__main__":
    try:main()
    except PilotError as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
