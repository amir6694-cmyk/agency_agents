"""Every sentence the engine can say, in English and Russian, keyed by a stable code."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict

LANGUAGES = ("en", "ru")
MONTHS_EN = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")


@dataclass
class Note:
    code: str
    params: Dict[str, Any] = field(default_factory=dict)


def grouped(value: float, lang: str = "en") -> str:
    text = f"{value:,.0f}"
    return text.replace(",", " ") if lang == "ru" else text


def aed(value: float, lang: str = "en") -> str:
    return f"{grouped(value, lang)} AED" if lang == "ru" else f"AED {grouped(value)}"


def long_date(day: date, lang: str = "en") -> str:
    if lang == "ru":
        return day.strftime("%d.%m.%Y")
    return f"{day.day} {MONTHS_EN[day.month - 1]} {day.year}"


def pct(value: float, signed: bool = False, lang: str = "en") -> str:
    text = f"{value * 100:+.1f}%" if signed else f"{value * 100:.1f}%"
    text = text.replace("-", "−")
    return text.replace(".", ",") if lang == "ru" else text


def rate(value: float, lang: str = "en") -> str:
    text = f"{value * 100:.4g}%"
    return text.replace(".", ",") if lang == "ru" else text


TEXT: Dict[str, Dict[str, str]] = {
    "en": {
        "value.scored": "{psf}/sqft is {gap} vs benchmark {benchmark}/sqft{basis}",
        "value.thin": "fewer than five comparable sales, or their number not recorded: a good score is held halfway to neutral",
        "value.no_size": "unscored: size not stated",
        "value.no_benchmark": "unscored: no sold-price benchmark",
        "yield.net": "net {net}, gross {gross}{basis}",
        "yield.gross": "gross {gross}; net estimated at {net} after typical costs because the service charge is not known{basis}",
        "yield.costs_unknown": "gross {gross}; net estimated at {net} after typical costs because acquisition costs could not be calculated{basis}",
        "yield.thin": "fewer than five rent contracts, or their number not recorded: a good score is held halfway to neutral",
        "yield.none": "unscored: no rent evidence",
        "fit.none": "no stated preferences to test",
        "fit.area_hit": "in a preferred area",
        "fit.area_miss": "outside the preferred areas",
        "fit.must_have": "{met}/{wanted} must-haves evidenced",
        "fit.size": "{size} sqft vs {wanted} wanted",
        "fit.size_unknown": "size not stated, so the {wanted} sqft minimum could not be tested",
        "fit.handover_ok": "handover in time",
        "fit.handover_late": "handover {late} months after the deadline",
        "fit.handover_unknown": "handover date not known",
        "trust.evidence_page": "its own page was opened",
        "trust.evidence_card": "seen as a card on a search page",
        "trust.evidence_lead": "search-engine lead, not opened",
        "trust.not_dated": "date seen not recorded",
        "trust.seen_future": "date seen is in the future",
        "trust.seen": "seen live {age} days ago",
        "trust.seen_today": "seen live today",
        "trust.permit": "advert permit captured",
        "trust.verified": "portal-verified",
        "trust.unverified": "not portal-verified",
        "trust.unchecked": "no permit or portal verification captured",
        "trust.corroborated": "price confirmed by the developer or a second broker",
        "trust.uncorroborated": "price not confirmed by the developer or a second broker",
        "trust.tier": "developer tier {tier}",
        "trust.tier_unknown": "developer's record not assessed",
        "trust.registered": "project found in the register",
        "trust.unregistered": "project not found in the register",
        "trust.registration_unchecked": "register not checked",
        "terms.resale": "a resale: the developer's plan is not the buyer's cash flow",
        "terms.na": "no developer payment plan",
        "terms.no_plan": "unscored: payment plan not recorded",
        "terms.no_date": "unscored: the plan defers payments to a handover whose date is not known",
        "terms.sale_type_unknown": "unscored: sale type not stated, so it is not known whether the developer's plan is the buyer's",
        "terms.scored": "plan is worth {pv} of the price today at {rate} a year; {before}% due before handover",
        "terms.waiver": "transfer fee of {rate} waived",
        "flag.analyst": "analyst's check: {text}",
        "flag.unverified_lead": "unverified lead: the page could not be opened, so price and availability are whatever a search engine last saw; open the link before relying on it",
        "flag.implausible_price": "asking price is {gap} vs the benchmark: confirm the unit exists, the size is right and it is not bait before relying on it",
        "flag.implausible_yield": "a gross yield of {gross} is not credible: check the rent figure and whether the price is the full price",
        "flag.registration_not_found": "the project was looked for in the register and not found: do not proceed until the developer supplies its registration and escrow details",
        "flag.overpriced": "asks {gap} against registered sales: only worth pursuing at a much lower price, so it is not shortlisted",
        "flag.thin_benchmark": "the benchmark rests on fewer than five sales, or their number was not recorded: treat the gap as indicative",
        "flag.from_price": "a 'from' price: it belongs to the smallest or least favoured unit, so it is not shortlisted until the price of a specific unit is in writing",
        "flag.completion_unknown": "completion status not stated: off-plan and ready prices are not comparable, so it is not shortlisted",
        "flag.bedrooms_unknown": "bedroom count not stated: the brief's limit could not be tested, so it is not shortlisted",
        "flag.type_unknown": "property type not stated: the brief's limit could not be tested, so it is not shortlisted",
        "flag.must_have_unmet": "required by the brief and not evidenced: {terms}; not shortlisted until it is",
        "flag.teaser_price": "a first sale asking {gap} against registered sales, and the price is not confirmed by the developer or a second broker: treat it as a teaser until it is",
        "flag.sale_type_unknown": "sale type not stated: costed as a resale, and the payment plan is not scored",
        "flag.behind_schedule": "{elapsed} of the registered construction period had passed at the last inspection with {built} built: do not plan around the stated date",
        "flag.budget_untested": "fees could not be calculated, so a budget that must cover them was tested against the price alone: not shortlisted",
        "flag.size_missing": "size not stated: price per sqft and value cannot be assessed",
        "flag.stale": "listed {days} days ago: may be sold, or negotiable",
        "flag.seen_in_future": "the date seen, {seen}, is after the valuation date: no credit given for freshness",
        "flag.registration_unchecked": "project registration and escrow not yet checked: not eligible for the shortlist until they are",
        "flag.developer_unproven": "developer has a thin or troubled delivery record",
        "flag.offplan_premium": "priced {premium} above ready homes of the same size nearby, more than the usual off-plan premium",
        "flag.register_overdue": "the register's completion date, {date}, has passed and the project is not finished",
        "flag.handover_passed": "the advertised handover, {handover}, has passed and the unit is still sold as off-plan",
        "flag.handover_mismatch": "the advert says handover {advert}, the register says {register}: the register's date is used",
        "flag.handover_unknown": "no handover date that is still ahead is known, so the brief's deadline could not be tested: not shortlisted",
        "flag.late_handover": "handover {handover} is {late} months after the brief's {wanted}",
        "flag.inspection_stale": "the register's progress figure was last inspected on {inspected}, over three months ago",
        "flag.resale_terms": "off-plan resale: ask the seller for the amount paid to date, any premium and the remaining schedule; the developer's plan is not your cash flow",
        "flag.post_handover_undated": "the post-handover share has no stated period: it is costed as due on handover",
        "flag.tenanted": "tenanted: vacant possession depends on the tenancy and statutory notice, so it is not shortlisted for own use",
        "flag.emirate_missing": "emirate not stated: fees could not be calculated and the outlay shown is the price only",
        "flag.cost_rates_unknown": "this emirate publishes no fee schedule: the outlay shown is the price only, obtain a written quote",
        "flag.cost_rates_partial": "this emirate publishes only its registration fee: agency commission and mortgage registration are not included, obtain a written quote",
        "flag.waiver_ignored": "a fee waiver was recorded on a resale: a developer cannot waive the fee on a resale, so it is charged in full",
        "flag.waiver_unconfirmed": "a fee waiver was recorded but the sale type was not: the fee is charged in full until the sale is confirmed as a first sale",
        "flag.offplan_finance": "off-plan: bank finance is capped at {cap} of the price and seldom available before handover, so costs are shown without a loan",
        "flag.ltv_capped": "the {ltv} loan asked for is above the Central Bank's {cap} ceiling for this purchase: figures use {cap}",
        "flag.non_resident_finance": "non-resident buyer: banks usually lend well below the Central Bank ceiling, get a pre-approval before relying on the loan",
        "flag.visa_margin": "priced within 5% of the {threshold} Golden Visa threshold: the test is on the registered value, so a negotiated discount can lose eligibility",
        "flag.visa_benchmark_below": "comparable sales imply about {implied}, under the {threshold} threshold: the asking price may be set for the visa rather than by the market",
        "flag.visa_conditions": "Golden Visa on a mortgaged or off-plan unit: official pages disagree on how much must be paid up, confirm with the emirate's land department or immigration authority first",
        "flag.transfer_seller_pays": "this island is registered by ADGM, whose rules put the 2% transfer fee on the seller: confirm it in the sale contract",
        "flag.transfer_split": "by default the 2% registration fee is shared equally with the seller; it is shown here in full on the buyer, as contracts often put it",
        "flag.trustee_quote": "the trustee office's fee for transferring an unbuilt unit is not published and is not in the total: get its quote",
        "flag.costs_exceed_budget": "price fits, but with acquisition costs the outlay is {outlay}",
        "flag.no_permit": "neither a permit number nor the portal's verification was captured: scan the advert's QR code or ask the broker for the permit before engaging",
        "flag.no_benchmark": "no sold-price benchmark supplied: the price is an asking price only",
        "flag.projected_rent": "rent is a projection for an unbuilt unit, not an achieved figure",
        "flag.low_turnover": "{sales} registered sales in this building in twelve months: reselling may be slow",
        "flag.card_only": "seen as a card on the portal's search page; its own page was not opened, so it is not shortlisted and the link leads to that search",
        "flag.advertised_lower": "the same or an identical unit is also advertised at {price}: see the other links",
        "reject.over_budget": "price {spend} is over the {budget} budget",
        "reject.over_budget_costs": "price plus acquisition costs {spend} is over the {budget} budget",
        "reject.under_budget": "price {price} is under the {minimum} minimum",
        "reject.market": "{completion} listing, brief asks for {market}",
        "reject.sale_type": "{sale}, brief asks for {asked}",
        "reject.emirate": "{emirate} is outside the brief",
        "reject.type": "property type '{type}' is outside the brief",
        "reject.beds_low": "{beds} bedrooms, brief needs at least {wanted}",
        "reject.beds_high": "{beds} bedrooms, brief allows at most {wanted}",
        "reject.area": "outside the areas the brief is restricted to",
        "reject.excluded": "matches the brief's exclusion '{term}'",
        "reject.handover": "handover {handover} is after the brief's deadline of {wanted}",
        "reject.golden_visa": "price is under the {threshold} Golden Visa property threshold",
        "cost.transfer_fee": "Transfer fee, {rate} of the price",
        "cost.transfer_fee_minimum": "Transfer fee, the minimum charge ({rate} of the price would be less)",
        "cost.transfer_fee_waived": "Transfer fee of {rate} waived by the developer: get the waiver in writing",
        "cost.transfer_fee_seller": "Transfer fee of {rate}: the seller's under ADGM rules",
        "cost.registration_fee": "Registration and title deed fees",
        "cost.trustee_fee": "Registration trustee fee, VAT included",
        "cost.agency_fee": "Agency commission, {rate} plus VAT",
        "cost.mortgage_registration": "Mortgage registration, {rate} of the loan plus a fixed fee",
    },
    "ru": {
        "value.scored": "{psf}/кв. фут — {gap} к бенчмарку {benchmark}/кв. фут{basis}",
        "value.thin": "сопоставимых сделок меньше пяти либо их число не записано: высокий балл сдвинут наполовину к нейтральному",
        "value.no_size": "не оценено: площадь не указана",
        "value.no_benchmark": "не оценено: нет бенчмарка по ценам сделок",
        "yield.net": "чистая {net}, валовая {gross}{basis}",
        "yield.gross": "валовая {gross}; чистая оценена в {net} после типовых расходов, так как сервисный сбор неизвестен{basis}",
        "yield.costs_unknown": "валовая {gross}; чистая оценена в {net} после типовых расходов, так как расходы на сделку рассчитать не удалось{basis}",
        "yield.thin": "договоров аренды меньше пяти либо их число не записано: высокий балл сдвинут наполовину к нейтральному",
        "yield.none": "не оценено: нет данных об аренде",
        "fit.none": "предпочтения для проверки не заданы",
        "fit.area_hit": "в предпочтительном районе",
        "fit.area_miss": "вне предпочтительных районов",
        "fit.must_have": "подтверждено обязательных условий: {met}/{wanted}",
        "fit.size": "{size} кв. футов при запросе от {wanted}",
        "fit.size_unknown": "площадь не указана, минимум {wanted} кв. футов проверить не удалось",
        "fit.handover_ok": "сдача в срок",
        "fit.handover_late": "сдача на {late} мес. позже срока",
        "fit.handover_unknown": "дата сдачи неизвестна",
        "trust.evidence_page": "страница объявления открыта",
        "trust.evidence_card": "карточка в поисковой выдаче портала",
        "trust.evidence_lead": "лид из поисковика, страница не открывалась",
        "trust.not_dated": "дата просмотра не записана",
        "trust.seen_future": "дата просмотра в будущем",
        "trust.seen": "просмотрено {age} дн. назад",
        "trust.seen_today": "просмотрено сегодня",
        "trust.permit": "номер разрешения на рекламу зафиксирован",
        "trust.verified": "верифицировано порталом",
        "trust.unverified": "не верифицировано порталом",
        "trust.unchecked": "нет ни разрешения, ни верификации портала",
        "trust.corroborated": "цена подтверждена застройщиком или вторым брокером",
        "trust.uncorroborated": "цена не подтверждена ни застройщиком, ни вторым брокером",
        "trust.tier": "застройщик {tier}-го эшелона",
        "trust.tier_unknown": "история застройщика не оценена",
        "trust.registered": "проект найден в реестре",
        "trust.unregistered": "проект в реестре не найден",
        "trust.registration_unchecked": "реестр не проверялся",
        "terms.resale": "переуступка: график застройщика не отражает платежи покупателя",
        "terms.na": "без рассрочки от застройщика",
        "terms.no_plan": "не оценено: график платежей не записан",
        "terms.no_date": "не оценено: график откладывает платежи до сдачи, дата которой неизвестна",
        "terms.sale_type_unknown": "не оценено: тип сделки не указан, неизвестно, действует ли для покупателя график застройщика",
        "terms.scored": "приведённая стоимость графика — {pv} цены при ставке {rate} годовых; до сдачи вносится {before}%",
        "terms.waiver": "регистрационный сбор {rate} оплачивает застройщик",
        "flag.analyst": "проверка аналитика: {text}",
        "flag.unverified_lead": "непроверенный лид: страницу открыть не удалось, цена и наличие — по последним данным поисковика; до любых выводов открыть ссылку",
        "flag.implausible_price": "цена {gap} к бенчмарку: до любых выводов подтвердить, что объект существует, площадь верна и это не приманка",
        "flag.implausible_yield": "валовая доходность {gross} неправдоподобна: проверить ставку аренды и то, полная ли это цена",
        "flag.registration_not_found": "проект искали в реестре и не нашли: не двигаться дальше, пока застройщик не предоставит регистрацию и эскроу-счёт",
        "flag.overpriced": "цена {gap} к зарегистрированным сделкам: имеет смысл только при существенно меньшей цене, поэтому объект не попадает в шорт-лист",
        "flag.thin_benchmark": "бенчмарк построен менее чем по пяти сделкам либо их число не записано: разницу считать ориентировочной",
        "flag.from_price": "цена «от»: она относится к самому маленькому или наименее удачному юниту, поэтому объект не попадает в шорт-лист, пока нет письменной цены конкретного юнита",
        "flag.completion_unknown": "статус готовности не указан: цены строящегося и готового жилья несопоставимы, поэтому объект не попадает в шорт-лист",
        "flag.bedrooms_unknown": "число спален не указано: ограничение из запроса проверить не удалось, объект не попадает в шорт-лист",
        "flag.type_unknown": "тип объекта не указан: ограничение из запроса проверить не удалось, объект не попадает в шорт-лист",
        "flag.must_have_unmet": "обязательное условие запроса не подтверждено: {terms}; до подтверждения объект не попадает в шорт-лист",
        "flag.teaser_price": "первичная продажа по цене {gap} к зарегистрированным сделкам, цена не подтверждена ни застройщиком, ни вторым брокером: до подтверждения считать приманкой",
        "flag.sale_type_unknown": "тип сделки не указан: расходы посчитаны как для перепродажи, график платежей не оценён",
        "flag.behind_schedule": "к последней инспекции прошло {elapsed} зарегистрированного срока строительства при готовности {built}: на заявленную дату не опираться",
        "flag.budget_untested": "сборы рассчитать не удалось, поэтому бюджет, который должен их покрывать, проверен только по цене: объект не попадает в шорт-лист",
        "flag.size_missing": "площадь не указана: цену за кв. фут и выгодность оценить нельзя",
        "flag.stale": "объявлению {days} дн.: возможно, продано — либо есть пространство для торга",
        "flag.seen_in_future": "дата просмотра {seen} позже даты оценки: актуальность не засчитана",
        "flag.registration_unchecked": "регистрация проекта и эскроу-счёт ещё не проверены: до проверки объект не попадает в шорт-лист",
        "flag.developer_unproven": "у застройщика короткая или проблемная история сдачи",
        "flag.offplan_premium": "цена на {premium} выше готового жилья того же формата рядом — больше обычной премии за строящееся",
        "flag.register_overdue": "плановая дата завершения по реестру, {date}, прошла, а проект не сдан",
        "flag.handover_passed": "заявленная сдача, {handover}, прошла, а объект всё ещё продаётся как строящийся",
        "flag.handover_mismatch": "в рекламе сдача {advert}, в реестре — {register}: в расчётах дата из реестра",
        "flag.handover_unknown": "нет даты сдачи, которая ещё не прошла, срок из запроса проверить не удалось: объект не попадает в шорт-лист",
        "flag.late_handover": "сдача {handover} — на {late} мес. позже требуемого срока {wanted}",
        "flag.inspection_stale": "готовность в реестре — по инспекции от {inspected}, ей больше трёх месяцев",
        "flag.resale_terms": "переуступка строящегося объекта: запросить у продавца внесённую сумму, премию и остаток графика; график застройщика не отражает ваши платежи",
        "flag.post_handover_undated": "срок рассрочки после сдачи не указан: эта доля учтена как подлежащая оплате при сдаче",
        "flag.tenanted": "объект с арендатором: освобождение зависит от договора аренды и срока уведомления, для собственного проживания в шорт-лист не попадает",
        "flag.emirate_missing": "эмират не указан: сборы рассчитать нельзя, в итоге только цена",
        "flag.cost_rates_unknown": "этот эмират не публикует тарифы: в итоге только цена, нужен письменный расчёт",
        "flag.cost_rates_partial": "этот эмират публикует только регистрационный сбор: комиссия агентства и регистрация ипотеки не включены, нужен письменный расчёт",
        "flag.waiver_ignored": "отмена сбора указана для вторичной сделки: застройщик не может отменить сбор при перепродаже, сбор учтён полностью",
        "flag.waiver_unconfirmed": "отмена сбора записана, а тип сделки нет: сбор учтён полностью, пока не подтверждено, что это первичная продажа",
        "flag.offplan_finance": "строящийся объект: банковское финансирование ограничено {cap} цены и до сдачи доступно редко, расходы показаны без кредита",
        "flag.ltv_capped": "запрошенный кредит {ltv} выше лимита Центробанка {cap} для такой покупки: в расчётах {cap}",
        "flag.non_resident_finance": "покупатель-нерезидент: банки обычно дают заметно меньше лимита Центробанка, до расчёта на кредит получить предодобрение",
        "flag.visa_margin": "цена в пределах 5% от порога {threshold} для Golden Visa: порог считается по зарегистрированной стоимости, скидка при торге может лишить права на визу",
        "flag.visa_benchmark_below": "по сопоставимым сделкам выходит около {implied} — ниже порога {threshold}: цена, возможно, выставлена под визу, а не по рынку",
        "flag.visa_conditions": "Golden Visa по объекту в ипотеке или в стройке: официальные страницы расходятся в том, какая сумма должна быть оплачена — сначала подтвердить в земельном департаменте или миграционной службе эмирата",
        "flag.transfer_seller_pays": "остров регистрирует ADGM, по правилам которого сбор 2% платит продавец: закрепить это в договоре",
        "flag.transfer_split": "по умолчанию сбор 2% делится с продавцом поровну; здесь он показан целиком на покупателе, как часто пишут в договорах",
        "flag.trustee_quote": "тариф регистрационного трасти за переоформление строящегося объекта не опубликован и в сумму не включён: запросить расчёт в офисе",
        "flag.costs_exceed_budget": "цена проходит, но с расходами на сделку итог {outlay}",
        "flag.no_permit": "не зафиксированы ни номер разрешения, ни верификация портала: до контакта отсканировать QR-код объявления или запросить разрешение у брокера",
        "flag.no_benchmark": "бенчмарк по сделкам не предоставлен: это только цена предложения",
        "flag.projected_rent": "аренда — прогноз для непостроенного объекта, а не фактическая ставка",
        "flag.low_turnover": "зарегистрированных сделок в здании за год: {sales}. Перепродажа может идти медленно",
        "flag.card_only": "объект виден карточкой в выдаче портала; его страница не открывалась, поэтому в шорт-лист он не попадает, а ссылка ведёт на эту выдачу",
        "flag.advertised_lower": "этот же или идентичный объект размещён также за {price}: см. остальные ссылки",
        "reject.over_budget": "цена {spend} выше бюджета {budget}",
        "reject.over_budget_costs": "цена с расходами на сделку {spend} выше бюджета {budget}",
        "reject.under_budget": "цена {price} ниже минимума {minimum}",
        "reject.market": "объект «{completion}», запрос — «{market}»",
        "reject.sale_type": "{sale}, запрос — {asked}",
        "reject.emirate": "{emirate} вне запроса",
        "reject.type": "тип объекта «{type}» вне запроса",
        "reject.beds_low": "спален: {beds}, требуется не менее {wanted}",
        "reject.beds_high": "спален: {beds}, допустимо не более {wanted}",
        "reject.area": "вне районов, которыми ограничен запрос",
        "reject.excluded": "подпадает под исключение «{term}»",
        "reject.handover": "сдача {handover} позже срока из запроса, {wanted}",
        "reject.golden_visa": "цена ниже порога {threshold} для Golden Visa",
        "cost.transfer_fee": "Регистрационный сбор, {rate} от цены",
        "cost.transfer_fee_minimum": "Регистрационный сбор, минимальная ставка ({rate} от цены было бы меньше)",
        "cost.transfer_fee_waived": "Регистрационный сбор {rate} оплачивает застройщик: получить это письменно",
        "cost.transfer_fee_seller": "Регистрационный сбор {rate}: по правилам ADGM платит продавец",
        "cost.registration_fee": "Сборы за регистрацию и титул",
        "cost.trustee_fee": "Услуги регистрационного трасти, включая НДС",
        "cost.agency_fee": "Комиссия агентства, {rate} плюс НДС",
        "cost.mortgage_registration": "Регистрация ипотеки, {rate} от суммы кредита плюс фиксированный сбор",
    },
}

UI: Dict[str, Dict[str, str]] = {
    "en": {
        "title": "Property Shortlist",
        "subtitle": "United Arab Emirates",
        "prepared_for": "Prepared for",
        "as_of": "As of",
        "budget": "Budget",
        "budget_with_costs": "including acquisition costs",
        "market": "Market",
        "purpose": "Purpose",
        "where": "Where",
        "anywhere": "any emirate",
        "received": "Listings reviewed",
        "unique": "Distinct offers",
        "ranked": "Passed the brief",
        "shortlisted": "Shortlisted",
        "rejected": "Rejected",
        "price": "Price",
        "psf": "per sqft",
        "gap": "vs sold benchmark",
        "gross_yield": "Gross yield",
        "net_yield": "Net yield",
        "outlay": "Total outlay",
        "own_funds": "Own funds needed",
        "cash_at_booking": "Due at booking, with fees",
        "sales_12m": "Sales in the building, 12 months",
        "score": "Score",
        "completeness": "Data completeness",
        "beds": "bed",
        "studio": "Studio",
        "sqft": "sqft",
        "handover": "Handover",
        "developer": "Developer",
        "agent": "Agent",
        "seen": "Seen",
        "permit": "Permit",
        "register": "Project register",
        "register_no": "No.",
        "register_started": "started",
        "register_built": "built",
        "register_inspected": "inspected",
        "register_due": "planned completion",
        "escrow": "escrow",
        "notes": "Analyst's notes",
        "sources": "Sources",
        "open_page": "Open listing",
        "open_card": "Open the search page showing this card",
        "open_lead": "Open the unverified lead",
        "also_listed": "Same or identical unit also advertised at",
        "criteria": "How it scored",
        "costs": "Acquisition costs",
        "flags": "Check before acting",
        "rejected_title": "Rejected against the brief",
        "method": "Method",
        "method_text": (
            "Each offer is scored from 0 to 100 on value (asking price per sqft against registered sales), yield, "
            "fit to the brief, trust (evidence level, how recently it was seen, permit or portal verification, and for "
            "off-plan the developer's record and the project's registration) and payment terms. A criterion with no "
            "data counts as a neutral 50 and lowers data completeness; one resting on few rows or an estimate counts "
            "for half. A criterion that does not apply to an offer is left out and the other weights are rescaled. "
            "Offers below 60% completeness are listed after the rated ones whatever their score. Only an "
            "offer whose own page was opened can be shortlisted. Asking prices are not transaction prices. Costs are "
            "estimates from fee schedules published as of {rates_as_of}; they leave out lender valuation and "
            "arrangement fees, developer no-objection and admin charges and, outside Dubai and Abu Dhabi, agency "
            "commission and mortgage registration. Confirm every figure against official sources before committing "
            "funds; title, contract and loan approval are for the conveyancer and the bank."
        ),
        "weights": "Weights",
        "unknown": "n/a",
        "none_ranked": "No listing passed the brief.",
        "costs_total": "costs",
        "outlay_total": "price plus costs",
        "own_funds_total": "own funds needed",
        "verdict.shortlist": "Shortlist",
        "verdict.consider": "Consider",
        "verdict.pass": "Pass",
        "verdict.needs_data": "Needs data",
        "verdict.verify_first": "Verify first",
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
        "sale.primary": "first sale",
        "sale.resale": "resale",
        "ready_premium": "vs ready homes nearby",
        "purpose.yield": "rental yield",
        "purpose.growth": "capital growth",
        "purpose.end_use": "own use",
        "purpose.golden_visa": "Golden Visa",
        "purpose.balanced": "balanced",
        "emirate.dubai": "Dubai",
        "emirate.abu_dhabi": "Abu Dhabi",
        "emirate.sharjah": "Sharjah",
        "emirate.ras_al_khaimah": "Ras Al Khaimah",
        "emirate.ajman": "Ajman",
        "emirate.umm_al_quwain": "Umm Al Quwain",
        "emirate.fujairah": "Fujairah",
        "type.apartment": "apartment",
        "type.villa": "villa",
        "type.townhouse": "townhouse",
        "type.penthouse": "penthouse",
        "type.duplex": "duplex",
        "type.plot": "plot",
        "type.office": "office",
    },
    "ru": {
        "title": "Подборка объектов",
        "subtitle": "Объединённые Арабские Эмираты",
        "prepared_for": "Клиент:",
        "as_of": "На дату",
        "budget": "Бюджет",
        "budget_with_costs": "с учётом расходов на сделку",
        "market": "Рынок",
        "purpose": "Цель",
        "where": "Где",
        "anywhere": "любой эмират",
        "received": "Рассмотрено объявлений",
        "unique": "Разных объектов",
        "ranked": "Прошли по запросу",
        "shortlisted": "В шорт-листе",
        "rejected": "Отклонено",
        "price": "Цена",
        "psf": "за кв. фут",
        "gap": "к бенчмарку сделок",
        "gross_yield": "Валовая доходность",
        "net_yield": "Чистая доходность",
        "outlay": "Итого к оплате",
        "own_funds": "Нужно собственных средств",
        "cash_at_booking": "При бронировании, с расходами",
        "sales_12m": "Сделок в здании за 12 мес.",
        "score": "Балл",
        "completeness": "Полнота данных",
        "beds": "спал.",
        "studio": "Студия",
        "sqft": "кв. футов",
        "handover": "Сдача",
        "developer": "Застройщик",
        "agent": "Агент",
        "seen": "Просмотрено",
        "permit": "Разрешение",
        "register": "Реестр проектов",
        "register_no": "№",
        "register_started": "начало",
        "register_built": "готовность",
        "register_inspected": "инспекция",
        "register_due": "плановое завершение",
        "escrow": "эскроу",
        "notes": "Заметки аналитика",
        "sources": "Источники",
        "open_page": "Открыть объявление",
        "open_card": "Открыть выдачу с этой карточкой",
        "open_lead": "Открыть непроверенный лид",
        "also_listed": "Этот же или идентичный объект размещён также",
        "criteria": "Из чего складывается балл",
        "costs": "Расходы на приобретение",
        "flags": "Проверить до действий",
        "rejected_title": "Отклонено по условиям запроса",
        "method": "Методика",
        "method_text": (
            "Каждый объект оценивается от 0 до 100 по выгодности (цена предложения за кв. фут к зарегистрированным "
            "сделкам), доходности, соответствию запросу, надёжности (уровень проверки, давность просмотра, разрешение "
            "или верификация портала, для строящихся — история застройщика и регистрация проекта) и условиям оплаты. "
            "Критерий без данных считается нейтральным (50) и снижает полноту данных; критерий, опирающийся на малое "
            "число строк или на оценку, засчитывается наполовину. Неприменимый к объекту критерий исключается, "
            "остальные веса пересчитываются. Объекты с полнотой ниже 60% идут после оценённых, "
            "каким бы ни был их балл. В шорт-лист попадает только объект, страница которого была открыта. Цены "
            "предложения — не цены сделок. Расходы — оценка по тарифам, опубликованным на {rates_as_of}; в них нет "
            "банковских комиссий за оценку и выдачу кредита, сборов застройщика за согласование и оформление, а вне "
            "Дубая и Абу-Даби — комиссии агентства и регистрации ипотеки. До перевода средств каждую цифру следует "
            "подтвердить по официальным источникам; титул, договор и одобрение кредита — зона юриста и банка."
        ),
        "weights": "Веса",
        "unknown": "н/д",
        "none_ranked": "Ни одно объявление не прошло по условиям запроса.",
        "costs_total": "расходы",
        "outlay_total": "цена с расходами",
        "own_funds_total": "нужно собственных средств",
        "verdict.shortlist": "Шорт-лист",
        "verdict.consider": "Рассмотреть",
        "verdict.pass": "Пропустить",
        "verdict.needs_data": "Нужны данные",
        "verdict.verify_first": "Сначала проверить",
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
        "sale.primary": "первичная продажа",
        "sale.resale": "перепродажа",
        "ready_premium": "к готовому жилью рядом",
        "purpose.yield": "арендный доход",
        "purpose.growth": "рост капитала",
        "purpose.end_use": "для себя",
        "purpose.golden_visa": "Golden Visa",
        "purpose.balanced": "сбалансированная",
        "emirate.dubai": "Дубай",
        "emirate.abu_dhabi": "Абу-Даби",
        "emirate.sharjah": "Шарджа",
        "emirate.ras_al_khaimah": "Рас-эль-Хайма",
        "emirate.ajman": "Аджман",
        "emirate.umm_al_quwain": "Умм-эль-Кайвайн",
        "emirate.fujairah": "Фуджейра",
        "type.apartment": "квартира",
        "type.villa": "вилла",
        "type.townhouse": "таунхаус",
        "type.penthouse": "пентхаус",
        "type.duplex": "дуплекс",
        "type.plot": "участок",
        "type.office": "офис",
    },
}

MONEY = ("psf", "benchmark", "outlay", "spend", "budget", "price", "minimum", "threshold", "implied")
SIGNED = ("gap", "premium")
SHARES = ("net", "gross", "pv", "elapsed", "built")
RATES = ("rate", "cap", "ltv")
DAYS = ("seen", "inspected")
LABELLED = {"completion": "market", "market": "market", "emirate": "emirate", "type": "type", "sale": "sale", "asked": "sale"}


def render(note: Note, lang: str = "en") -> str:
    labels = UI[lang]
    shown: Dict[str, Any] = {}
    for key, value in note.params.items():
        if key in MONEY:
            shown[key] = aed(value, lang)
        elif key in SIGNED:
            shown[key] = pct(value, signed=True, lang=lang)
        elif key in SHARES:
            shown[key] = pct(value, lang=lang)
        elif key in RATES:
            shown[key] = rate(value, lang)
        elif key in DAYS:
            shown[key] = long_date(date.fromisoformat(value), lang)
        elif key in LABELLED:
            shown[key] = labels.get(f"{LABELLED[key]}.{value}", str(value).replace("_", " "))
        elif key == "basis":
            shown[key] = f" ({value})" if value else ""
        elif isinstance(value, float):
            shown[key] = grouped(value, lang)
        else:
            shown[key] = value
    return TEXT[lang][note.code].format(**shown)
