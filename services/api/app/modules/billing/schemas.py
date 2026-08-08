from __future__ import annotations

from pydantic import BaseModel


class UsageByType(BaseModel):
    event_type: str
    unit: str
    total_quantity: float
    event_count: int


class CampaignBudget(BaseModel):
    campaign_id: str
    campaign_name: str
    daily_budget_paise: int
    spent_today_paise: int


class UsageSummary(BaseModel):
    usage_by_type: list[UsageByType]
    total_calls: int
    total_call_seconds: float
    campaign_budgets: list[CampaignBudget]
