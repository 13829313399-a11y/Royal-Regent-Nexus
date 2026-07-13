import json
from datetime import datetime
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.pricing import PricingQuote
from app.schemas.pricing import (
    DiscountRule,
    PricingContext,
    PricingInputOut,
    PricingLine,
    PricingLineResult,
    PricingQuoteCreate,
    PricingQuoteOut,
    PricingResult,
    RebateResult,
    RebateTier,
    TaxResult,
)


PRICING_CONTEXTS = {
    "buzzbee": PricingContext(
        customer_id="buzzbee",
        customer_name="BuzzBee",
        currency="HKD",
        tax_rate=0,
        rules=[
            DiscountRule(id="bb-handling", label="订单处理费", kind="markup", value=80),
            DiscountRule(id="bb-plastic-volume", label="塑胶大货 2% 优惠", product_line="塑胶", kind="percent", value=2, min_qty=5000),
        ],
        rebate_tiers=[RebateTier(threshold=50000, rate=1), RebateTier(threshold=100000, rate=2)],
    ),
    "disney": PricingContext(
        customer_id="disney",
        customer_name="迪士尼",
        currency="HKD",
        tax_rate=0,
        rules=[
            DiscountRule(id="ds-compliance", label="合规处理费", kind="markup", value=150),
            DiscountRule(id="ds-toy-volume", label="玩具大货 1.5% 优惠", product_line="玩具", kind="percent", value=1.5, min_qty=3000),
        ],
        rebate_tiers=[RebateTier(threshold=80000, rate=1), RebateTier(threshold=160000, rate=1.8)],
    ),
    "dicky": PricingContext(
        customer_id="dicky",
        customer_name="Dickie",
        currency="HKD",
        tax_rate=0,
        rules=[
            DiscountRule(id="dk-handling", label="订单处理费", kind="markup", value=100),
            DiscountRule(id="dk-volume", label="大货 2% 优惠", kind="percent", value=2, min_qty=5000),
        ],
        rebate_tiers=[RebateTier(threshold=60000, rate=1), RebateTier(threshold=120000, rate=2)],
    ),
    "caixing": PricingContext(
        customer_id="caixing",
        customer_name="彩星",
        currency="HKD",
        tax_rate=0,
        rules=[
            DiscountRule(id="cx-small-order", label="小单处理费", kind="markup", value=60),
            DiscountRule(id="cx-plastic-volume", label="塑胶大货 2.5% 优惠", product_line="塑胶", kind="percent", value=2.5, min_qty=5000),
        ],
        rebate_tiers=[RebateTier(threshold=50000, rate=0.8), RebateTier(threshold=100000, rate=1.5)],
    ),
}

RULE_ORDER = {"markup": 0, "percent": 1, "fixed": 2}


def round_money(value: float) -> float:
    return round(value + 1e-12, 2)


def get_pricing_context(customer_id: str) -> PricingContext:
    context = PRICING_CONTEXTS.get(customer_id.strip().lower())
    if context is None:
        raise HTTPException(status_code=404, detail="未配置该客户的内部报价规则")
    return context.model_copy(deep=True)


def calculate_pricing(lines: list[PricingLine], context: PricingContext) -> PricingResult:
    calculated_lines: list[PricingLineResult] = []
    ordered_rules = sorted(enumerate(context.rules), key=lambda item: (RULE_ORDER[item[1].kind], item[0]))

    for line in lines:
        gross = line.qty * line.unit_price
        amount = gross
        applied_rules: list[str] = []
        for _, rule in ordered_rules:
            if rule.product_line and rule.product_line != line.product_line:
                continue
            if rule.min_qty is not None and line.qty < rule.min_qty:
                continue
            if rule.kind == "markup":
                amount += rule.value
            elif rule.kind == "percent":
                amount -= amount * rule.value / 100
            else:
                amount -= rule.value
            applied_rules.append(rule.id)

        calculated_lines.append(PricingLineResult(
            **line.model_dump(),
            gross=round_money(gross),
            after_discount=round_money(max(0, amount)),
            applied_rules=applied_rules,
        ))

    subtotal = round_money(sum(line.after_discount for line in calculated_lines))
    tier = next(
        (candidate for candidate in reversed(sorted(context.rebate_tiers, key=lambda item: item.threshold)) if candidate.threshold <= subtotal),
        None,
    )
    rebate_amount = round_money(subtotal * tier.rate / 100) if tier else 0
    taxable = round_money(subtotal - rebate_amount)
    tax_amount = round_money(taxable * context.tax_rate / 100)
    return PricingResult(
        lines=calculated_lines,
        subtotal=subtotal,
        rebate=RebateResult(amount=rebate_amount, tier=tier),
        tax=TaxResult(amount=tax_amount, rate=context.tax_rate),
        total=round_money(taxable + tax_amount),
        currency=context.currency,
    )


def _results_match(local: object, server: object, tolerance: float = 0.005) -> bool:
    if isinstance(local, (int, float)) and isinstance(server, (int, float)):
        return abs(float(local) - float(server)) <= tolerance
    if isinstance(local, dict) and isinstance(server, dict):
        return local.keys() == server.keys() and all(_results_match(local[key], server[key], tolerance) for key in local)
    if isinstance(local, list) and isinstance(server, list):
        return len(local) == len(server) and all(_results_match(left, right, tolerance) for left, right in zip(local, server))
    return local == server


def quote_to_out(quote: PricingQuote) -> PricingQuoteOut:
    return PricingQuoteOut(
        id=quote.id,
        factory_id=quote.factory_id,
        customer_id=quote.customer_id,
        customer_name=quote.customer_name,
        project_name=quote.project_name,
        status=quote.status,
        input=PricingInputOut.model_validate_json(quote.input_json),
        context=PricingContext.model_validate_json(quote.context_json),
        result=PricingResult.model_validate_json(quote.result_json),
        created_by=quote.created_by,
        created_at=quote.created_at,
    )


def create_quote(db: Session, payload: PricingQuoteCreate, user_id: str) -> PricingQuoteOut:
    context = get_pricing_context(payload.customer_id)
    server_result = calculate_pricing(payload.lines, context)
    if not _results_match(payload.local_result.model_dump(), server_result.model_dump()):
        raise HTTPException(status_code=409, detail="前端测算结果与服务器复算结果不一致")

    quote = PricingQuote(
        id=f"IQ-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:6].upper()}",
        factory_id=payload.factory_id,
        customer_id=context.customer_id,
        customer_name=context.customer_name,
        project_name=payload.project_name,
        status="draft",
        input_json=json.dumps(PricingInputOut(customer_id=context.customer_id, lines=payload.lines).model_dump(), ensure_ascii=False),
        context_json=context.model_dump_json(),
        result_json=server_result.model_dump_json(),
        created_by=user_id,
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    db.add(quote)
    db.commit()
    db.refresh(quote)
    return quote_to_out(quote)


def list_quotes(db: Session, factory_id: str, customer_id: str | None = None) -> list[PricingQuoteOut]:
    statement = select(PricingQuote).where(PricingQuote.factory_id == factory_id)
    if customer_id:
        statement = statement.where(PricingQuote.customer_id == customer_id)
    statement = statement.order_by(PricingQuote.created_at.desc())
    return [quote_to_out(quote) for quote in db.scalars(statement).all()]
