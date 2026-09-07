"""
Тонкая обёртка над Bitrix24 REST API (через входящий вебхук).
"""

import os
import requests

BITRIX_WEBHOOK_URL = os.getenv("BITRIX_WEBHOOK_URL", "").rstrip("/")


def _call(method: str, params: dict | None = None) -> dict:
    if not BITRIX_WEBHOOK_URL:
        raise RuntimeError("BITRIX_WEBHOOK_URL не задан в .env")

    url = f"{BITRIX_WEBHOOK_URL}/{method}.json"
    resp = requests.post(url, json=params or {}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"Bitrix error: {data.get('error_description', data['error'])}")
    return data


def get_deals_by_stage(stage_id: str, category_id: str | None = None, limit: int = 50) -> list[dict]:
    """Возвращает список сделок на заданной стадии."""
    filter_ = {"STAGE_ID": stage_id}
    if category_id not in (None, "", "None"):
        filter_["CATEGORY_ID"] = category_id

    params = {
        "filter": filter_,
        "select": ["ID", "TITLE", "OPPORTUNITY", "CURRENCY_ID", "CONTACT_ID", "COMPANY_ID"],
        "order": {"ID": "DESC"},
    }

    deals: list[dict] = []
    start = 0
    while True:
        params["start"] = start
        data = _call("crm.deal.list", params)
        deals.extend(data.get("result", []))
        nxt = data.get("next")
        if not nxt or len(deals) >= limit:
            break
        start = nxt
    return deals[:limit]


def get_deal(deal_id: int) -> dict:
    data = _call("crm.deal.get", {"id": deal_id})
    return data.get("result", {})


def get_contact_name(contact_id: int) -> str:
    if not contact_id:
        return ""
    try:
        data = _call("crm.contact.get", {"id": contact_id})
        c = data.get("result", {})
        return " ".join(filter(None, [c.get("NAME"), c.get("LAST_NAME")])).strip()
    except Exception:
        return ""


def list_deal_stages(category_id: str | None = None) -> list[dict]:
    """Вспомогательный метод — помогает узнать STAGE_ID нужной стадии."""
    params = {}
    if category_id not in (None, "", "None"):
        params["id"] = category_id
    data = _call("crm.dealcategory.stage.list", params)
    return data.get("result", [])
