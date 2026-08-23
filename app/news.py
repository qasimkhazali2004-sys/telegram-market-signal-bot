from __future__ import annotations
from app.models import NewsStatus

class NewsProvider:
    async def status(self, symbol: str, block_minutes: int) -> NewsStatus:
        raise NotImplementedError

class DisabledNewsProvider(NewsProvider):
    async def status(self, symbol: str, block_minutes: int) -> NewsStatus:
        return NewsStatus(False, "فلتر الأخبار غير مفعل")

class FailClosedNewsProvider(NewsProvider):
    async def status(self, symbol: str, block_minutes: int) -> NewsStatus:
        return NewsStatus(
            True,
            "NEWS RISK – NO TRADE",
            "لم يتم ربط مزود أخبار موثوق؛ الفلتر مفعل ولذلك يتم منع الدخول.",
        )
