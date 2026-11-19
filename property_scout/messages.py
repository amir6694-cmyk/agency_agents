"""Every sentence the engine can say, in English and Russian, keyed by a stable code."""

from dataclasses import dataclass, field
from typing import Any, Dict

LANGUAGES = ("en", "ru")


@dataclass
class Note:
    code: str
    params: Dict[str, Any] = field(default_factory=dict)


def aed(value: float, lang: str = "en") -> str:
    if lang == "ru":
        return f"{value:,.0f}".replace(",", " ") + " AED"
    return f"AED {value:,.0f}"


def pct(value: float, signed: bool = False) -> str:
    return f"{value * 100:+.1f}%" if signed else f"{value * 100:.1f}%"


TEXT: Dict[str, Dict[str, str]] = {
    "en": {
        "value.scored": "{psf}/sqft is {gap} vs benchmark {benchmark}/sqft{basis}",
        "value.no_size": "unscored: size not stated",
        "value.no_benchmark": "unscored: no sold-price benchmark",
        "yield.net": "net {net}, gross {gross}{basis}",
        "yield.gross": "gross {gross}, net unknown{basis}",
        "yield.none": "unscored: no rent evidence",
        "fit.none": "no stated preferences to test",
        "fit.area_hit": "in a preferred area",
        "fit.area_miss": "outside the preferred areas",
        "fit.must_have": "{met}/{wanted} must-haves evidenced",
        "fit.size": "{size} sqft vs {wanted} wanted",
        "fit.handover_ok": "handover in time",
        "fit.handover_late": "handover {late} months after the deadline",
        "trust.none": "unscored: no verification evidence",
        "trust.permit": "advert permit shown",
        "trust.verified": "portal-verified",
        "trust.unverified": "not portal-verified",
        "trust.seen": "seen live {age} days ago",
        "trust.seen_today": "seen live today",
        "trust.tier": "developer tier {tier}",
        "trust.registered": "project registration verified",
        "trust.unregistered": "project registration not found",
        "terms.na": "no developer payment plan",
        "terms.missing": "unscored: payment plan or handover date missing",
        "terms.scored": "plan is worth {pv} of the price today at {rate} a year; {before}% due before handover",
        "flag.implausible_price": "asking price is {gap} vs the benchmark: confirm the unit exists, the size is right and it is not bait before relying on it",
        "flag.registration_not_found": "project registration or escrow could not be found: do not proceed until the developer supplies it",
        "flag.completion_unknown": "completion status not stated: off-plan and ready prices are not comparable",
        "flag.size_missing": "size not stated: price per sqft and value cannot be assessed",
        "flag.no_permit": "advertising permit number not captured: scan the advert's QR code or ask the broker for it before engaging",
        "flag.stale": "listed {days} days ago: may be sold, or negotiable",
        "flag.registration_unchecked": "project registration and escrow not yet verified",
        "flag.developer_unproven": "developer has a thin or troubled delivery record",
        "flag.offplan_premium": "priced {premium} above ready homes of the same size nearby: off-plan usually carries a premium, this one is large",
        "flag.late_handover": "handover {handover} is {late} months after the brief's {wanted}",
        "flag.tenanted": "tenanted: vacant possession depends on the tenancy and statutory notice",
        "flag.costs_exceed_budget": "price fits, but with acquisition costs the outlay is {outlay}",
        "flag.no_benchmark": "no sold-price benchmark supplied: the price is an asking price only",
        "flag.projected_rent": "rent is a projection for an unbuilt unit, not an achieved figure",
        "flag.not_dated": "no date recorded for when the listing was seen live",
        "flag.cost_rates_unknown": "this emirate publishes no fee schedule: the outlay shown is the price only, obtain a written quote",
        "flag.cost_rates_indicative": "this emirate publishes only part of its fee schedule: costs are indicative and exclude agency commission, obtain a written quote",
        "flag.offplan_finance": "off-plan: bank finance is capped at {cap} of the price, so costs are shown without a loan",
        "flag.ltv_over_cap": "the {ltv} loan asked for is above the Central Bank's {cap} ceiling for this purchase",
        "flag.golden_visa_conditions": "Golden Visa on a mortgaged or off-plan unit: official pages disagree on how much must be paid up, confirm with DLD or GDRFA before relying on it",
        "reject.over_budget": "price {spend} is over the {budget} budget",
        "reject.over_budget_costs": "price plus acquisition costs {spend} is over the {budget} budget",
        "reject.under_budget": "price {price} is under the {minimum} minimum",
        "reject.market": "{completion} listing, brief asks for {market}",
        "reject.emirate": "emirate {emirate} is outside the brief",
        "reject.type": "property type {type} is outside the brief",
        "reject.beds_low": "{beds} bedrooms, brief needs at least {wanted}",
        "reject.beds_high": "{beds} bedrooms, brief allows at most {wanted}",
        "reject.area": "outside the areas the brief is restricted to",
        "reject.excluded": "matches the brief's exclusion '{term}'",
        "reject.golden_visa": "price is under the {threshold} Golden Visa property threshold",
        "cost.transfer_fee": "Transfer fee, {rate} of the price",
        "cost.transfer_fee_waived": "Transfer fee of {rate} waived by the developer: get the waiver in writing",
        "cost.registration_fee": "Registration and title deed fees",
        "cost.trustee_fee": "Registration trustee fee, VAT included",
        "cost.agency_fee": "Agency commission, {rate} plus VAT",
        "cost.mortgage_registration": "Mortgage registration, {rate} of the loan plus a fixed fee",
    },
    "ru": {
        "value.scored": "{psf}/кв.фут — {gap} к бенчмарку {benchmark}/кв.фут{basis}",
        "value.no_size": "не оценено: площадь не указана",
        "value.no_benchmark": "не оценено: нет бенчмарка по ценам сделок",
        "yield.net": "чистая {net}, валовая {gross}{basis}",
        "yield.gross": "валовая {gross}, чистая неизвестна{basis}",
        "yield.none": "не оценено: нет данных об аренде",
        "fit.none": "предпочтения для проверки не заданы",
        "fit.area_hit": "в предпочтительном районе",
        "fit.area_miss": "вне предпочтительных районов",
        "fit.must_have": "подтверждено обязательных условий: {met}/{wanted}",
        "fit.size": "{size} кв.футов при запросе от {wanted}",
        "fit.handover_ok": "сдача в срок",
        "fit.handover_late": "сдача на {late} мес. позже срока",
        "trust.none": "не оценено: нет данных проверки",
        "trust.permit": "номер разрешения на рекламу указан",
        "trust.verified": "верифицировано порталом",
        "trust.unverified": "не верифицировано порталом",
        "trust.seen": "активность проверена {age} дн. назад",
        "trust.seen_today": "активность проверена сегодня",
        "trust.tier": "застройщик {tier}-го эшелона",
        "trust.registered": "регистрация проекта подтверждена",
        "trust.unregistered": "регистрация проекта не найдена",
        "terms.na": "без рассрочки от застройщика",
        "terms.missing": "не оценено: нет графика платежей или даты сдачи",
        "terms.scored": "приведённая стоимость графика — {pv} цены при ставке {rate} годовых; до сдачи вносится {before}%",
        "flag.implausible_price": "цена {gap} к бенчмарку: до любых выводов подтвердить, что объект существует, площадь верна и это не приманка",
        "flag.registration_not_found": "регистрация проекта или эскроу-счёт не найдены: не двигаться дальше, пока застройщик их не предоставит",
        "flag.completion_unknown": "статус готовности не указан: цены строящегося и готового жилья несопоставимы",
        "flag.size_missing": "площадь не указана: цену за кв.фут и выгодность оценить нельзя",
        "flag.no_permit": "номер разрешения на рекламу не зафиксирован: до контакта отсканировать QR-код объявления или запросить номер у брокера",
        "flag.stale": "объявлению {days} дн.: возможно, продано — либо есть пространство для торга",
        "flag.registration_unchecked": "регистрация проекта и эскроу-счёт ещё не проверены",
        "flag.developer_unproven": "у застройщика короткая или проблемная история сдачи",
        "flag.offplan_premium": "цена на {premium} выше готового жилья того же формата рядом: премия за стройку обычна, но здесь она велика",
        "flag.late_handover": "сдача {handover} — на {late} мес. позже требуемого срока {wanted}",
        "flag.tenanted": "объект с арендатором: освобождение зависит от договора аренды и срока уведомления",
        "flag.costs_exceed_budget": "цена проходит, но с расходами на сделку итог {outlay}",
        "flag.no_benchmark": "бенчмарк по сделкам не предоставлен: это только цена предложения",
        "flag.projected_rent": "аренда — прогноз для непостроенного объекта, а не фактическая ставка",
        "flag.not_dated": "не записана дата, когда объявление было активно",
        "flag.cost_rates_unknown": "этот эмират не публикует тарифы: в итоге только цена, нужен письменный расчёт",
        "flag.cost_rates_indicative": "этот эмират публикует тарифы лишь частично: расходы ориентировочные и без комиссии агентства, нужен письменный расчёт",
        "flag.offplan_finance": "строящийся объект: банковское финансирование ограничено {cap} цены, расходы показаны без кредита",
        "flag.ltv_over_cap": "запрошенный кредит {ltv} выше лимита Центробанка {cap} для такой покупки",
        "flag.golden_visa_conditions": "Golden Visa по объекту в ипотеке или в стройке: официальные страницы расходятся в том, какая сумма должна быть оплачена — подтвердить в DLD или GDRFA",
        "reject.over_budget": "цена {spend} выше бюджета {budget}",
        "reject.over_budget_costs": "цена с расходами на сделку {spend} выше бюджета {budget}",
        "reject.under_budget": "цена {price} ниже минимума {minimum}",
        "reject.market": "объект «{completion}», запрос — «{market}»",
        "reject.emirate": "эмират {emirate} вне запроса",
        "reject.type": "тип объекта {type} вне запроса",
        "reject.beds_low": "спален: {beds}, требуется не менее {wanted}",
        "reject.beds_high": "спален: {beds}, допустимо не более {wanted}",
        "reject.area": "вне районов, которыми ограничен запрос",
        "reject.excluded": "подпадает под исключение «{term}»",
        "reject.golden_visa": "цена ниже порога {threshold} для Golden Visa",
        "cost.transfer_fee": "Регистрационный сбор, {rate} от цены",
        "cost.transfer_fee_waived": "Регистрационный сбор {rate} оплачивает застройщик: получить это письменно",
        "cost.registration_fee": "Сборы за регистрацию и титул",
        "cost.trustee_fee": "Услуги регистрационного трасти, включая НДС",
        "cost.agency_fee": "Комиссия агентства, {rate} плюс НДС",
        "cost.mortgage_registration": "Регистрация ипотеки, {rate} от суммы кредита плюс фиксированный сбор",
    },
}

MONEY_PARAMS = ("psf", "benchmark", "outlay", "spend", "budget", "price", "minimum", "threshold")
SIGNED_PARAMS = ("gap", "premium")
SHARE_PARAMS = ("net", "gross", "pv")
RATE_PARAMS = ("rate", "cap", "ltv")


def render(note: Note, lang: str = "en") -> str:
    shown: Dict[str, Any] = {}
    for key, value in note.params.items():
        if key in MONEY_PARAMS:
            shown[key] = aed(value, lang)
        elif key in SIGNED_PARAMS:
            shown[key] = pct(value, signed=True)
        elif key in SHARE_PARAMS:
            shown[key] = pct(value)
        elif key in RATE_PARAMS:
            shown[key] = f"{value * 100:.4g}%"
        elif key == "basis":
            shown[key] = f" ({value})" if value else ""
        elif isinstance(value, float):
            shown[key] = f"{value:,.0f}"
        else:
            shown[key] = value
    return TEXT[lang][note.code].format(**shown)


UI: Dict[str, Dict[str, str]] = {
    "en": {
        "title": "Property Shortlist",
        "subtitle": "United Arab Emirates",
        "prepared_for": "Prepared for",
        "as_of": "As of",
        "brief": "Brief",
        "budget": "Budget",
        "budget_with_costs": "including acquisition costs",
        "market": "Market",
        "purpose": "Purpose",
        "where": "Where",
        "anywhere": "any emirate",
        "received": "Listings reviewed",
        "unique": "Unique units",
        "ranked": "Passed the brief",
        "shortlisted": "Shortlisted",
        "rejected": "Rejected",
        "price": "Price",
        "psf": "per sqft",
        "gap": "vs sold benchmark",
        "gross_yield": "Gross yield",
        "net_yield": "Net yield",
        "outlay": "Total outlay",
        "upfront_cash": "Own funds needed",
        "costs_total": "costs",
        "outlay_total": "price plus costs",
        "costs_incomplete": "no cost table for this emirate: the figures above are incomplete",
        "score": "Score",
        "confidence": "Evidence",
        "beds": "bed",
        "studio": "Studio",
        "sqft": "sqft",
        "handover": "Handover",
        "developer": "Developer",
        "open_listing": "Open listing",
        "also_listed": "Same or identical unit also advertised at",
        "criteria": "How it scored",
        "costs": "Acquisition costs",
        "flags": "Check before acting",
        "rejected_title": "Rejected against the brief",
        "method": "Method",
        "method_text": (
            "Each unit is scored from 0 to 100 on value (asking price per sqft against a sold-price benchmark), "
            "yield, fit to the brief, trust (permit, verification, recency, developer and registration for off-plan) "
            "and payment terms. A criterion with no data counts as a neutral 50 and lowers the evidence figure. "
            "Asking prices are not transaction prices. Costs are estimates from published fee schedules as of {rates_as_of}; "
            "confirm every figure against official sources before committing funds."
        ),
        "weights": "Weights",
        "unknown": "n/a",
        "none_ranked": "No listing passed the brief.",
        "verdict.shortlist": "Shortlist",
        "verdict.consider": "Consider",
        "verdict.verify_first": "Verify first",
        "verdict.pass": "Pass",
        "criterion.value": "Value",
        "criterion.yield": "Yield",
        "criterion.fit": "Fit",
        "criterion.trust": "Trust",
        "criterion.terms": "Terms",
        "severity.critical": "Critical",
        "severity.warning": "Warning",
        "severity.info": "Note",
        "market.offplan": "off-plan",
        "market.ready": "ready",
        "market.any": "off-plan or ready",
        "purpose.yield": "rental yield",
        "purpose.growth": "capital growth",
        "purpose.end_use": "own use",
        "purpose.golden_visa": "Golden Visa",
        "purpose.balanced": "balanced",
    },
    "ru": {
        "title": "Подборка объектов",
        "subtitle": "Объединённые Арабские Эмираты",
        "prepared_for": "Подготовлено для",
        "as_of": "На дату",
        "brief": "Запрос",
        "budget": "Бюджет",
        "budget_with_costs": "с учётом расходов на сделку",
        "market": "Рынок",
        "purpose": "Цель",
        "where": "Где",
        "anywhere": "любой эмират",
        "received": "Рассмотрено объявлений",
        "unique": "Уникальных объектов",
        "ranked": "Прошли по запросу",
        "shortlisted": "В шорт-листе",
        "rejected": "Отклонено",
        "price": "Цена",
        "psf": "за кв.фут",
        "gap": "к бенчмарку сделок",
        "gross_yield": "Валовая доходность",
        "net_yield": "Чистая доходность",
        "outlay": "Итого к оплате",
        "upfront_cash": "Нужно собственных средств",
        "costs_total": "расходы",
        "outlay_total": "цена с расходами",
        "costs_incomplete": "для этого эмирата нет таблицы сборов: цифры выше неполные",
        "score": "Балл",
        "confidence": "Доказательность",
        "beds": "спал.",
        "studio": "Студия",
        "sqft": "кв.футов",
        "handover": "Сдача",
        "developer": "Застройщик",
        "open_listing": "Открыть объявление",
        "also_listed": "Этот же или идентичный объект размещён также",
        "criteria": "Из чего складывается балл",
        "costs": "Расходы на приобретение",
        "flags": "Проверить до действий",
        "rejected_title": "Отклонено по условиям запроса",
        "method": "Методика",
        "method_text": (
            "Каждый объект оценивается от 0 до 100 по выгодности (цена предложения за кв.фут к бенчмарку цен сделок), "
            "доходности, соответствию запросу, надёжности (разрешение, верификация, актуальность, для строящихся — "
            "застройщик и регистрация проекта) и условиям оплаты. Критерий без данных считается нейтральным (50) "
            "и снижает показатель доказательности. Цены предложения — не цены сделок. Расходы — оценка по опубликованным "
            "тарифам на {rates_as_of}; до перевода средств каждую цифру следует подтвердить по официальным источникам."
        ),
        "weights": "Веса",
        "unknown": "н/д",
        "none_ranked": "Ни одно объявление не прошло по условиям запроса.",
        "verdict.shortlist": "Шорт-лист",
        "verdict.consider": "Рассмотреть",
        "verdict.verify_first": "Сначала проверить",
        "verdict.pass": "Пропустить",
        "criterion.value": "Выгодность",
        "criterion.yield": "Доходность",
        "criterion.fit": "Соответствие",
        "criterion.trust": "Надёжность",
        "criterion.terms": "Условия оплаты",
        "severity.critical": "Критично",
        "severity.warning": "Внимание",
        "severity.info": "Примечание",
        "market.offplan": "строящееся",
        "market.ready": "готовое",
        "market.any": "строящееся или готовое",
        "purpose.yield": "арендный доход",
        "purpose.growth": "рост капитала",
        "purpose.end_use": "для себя",
        "purpose.golden_visa": "Golden Visa",
        "purpose.balanced": "сбалансированная",
    },
}
