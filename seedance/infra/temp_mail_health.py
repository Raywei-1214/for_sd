import json
from pathlib import Path

from seedance.core.logger import get_logger

logger = get_logger()


class TempMailHealthStore:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.data = self._load()

    def _load(self) -> dict:
        try:
            if self.file_path.exists():
                return json.loads(self.file_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"加载临时邮箱健康度失败: {exc}")

        return {
            "rotation_index": 0,
            "providers": {},
        }

    def _save(self) -> None:
        try:
            self.file_path.write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning(f"保存临时邮箱健康度失败: {exc}")

    def _get_provider_stats(self, provider_name: str) -> dict:
        providers = self.data.setdefault("providers", {})
        provider_stats = providers.setdefault(
            provider_name,
            {
                "success_count": 0,
                "failure_count": 0,
                "consecutive_failures": 0,
            },
        )
        return provider_stats

    def _health_score(self, provider_name: str) -> float:
        stats = self._get_provider_stats(provider_name)
        success_count = stats["success_count"]
        failure_count = stats["failure_count"]
        consecutive_failures = stats["consecutive_failures"]

        success_rate = (success_count + 1) / (success_count + failure_count + 2)
        penalty = min(consecutive_failures * 0.08, 0.32)
        return max(success_rate - penalty, 0.05)

    def build_provider_plan(self, provider_names: list[str], total_count: int) -> list[str]:
        if not provider_names or total_count <= 0:
            return []

        ranked_provider_names = sorted(
            provider_names,
            key=lambda provider_name: self._health_score(provider_name),
            reverse=True,
        )

        weighted_cycle: list[str] = []
        for provider_name in ranked_provider_names:
            weighted_cycle.append(provider_name)

        for provider_name in ranked_provider_names:
            score = self._health_score(provider_name)
            if score >= 0.72:
                weighted_cycle.append(provider_name)
            if score >= 0.84:
                weighted_cycle.append(provider_name)

        rotation_index = self.data.get("rotation_index", 0)
        plan = []

        # ================================
        # 所有站点至少在基础轮盘里保留一次
        # 高健康站点只是在 bonus 段多分配，不会完全垄断
        # ================================
        for offset in range(total_count):
            provider_index = (rotation_index + offset) % len(weighted_cycle)
            plan.append(weighted_cycle[provider_index])

        self.data["rotation_index"] = (rotation_index + total_count) % len(weighted_cycle)
        self._save()
        return plan

    def record_provider_result(
        self,
        provider_name: str,
        *,
        success: bool,
        hard_failure: bool,
    ) -> None:
        stats = self._get_provider_stats(provider_name)

        if success:
            stats["success_count"] += 1
            stats["consecutive_failures"] = 0
            self._save()
            return

        if hard_failure:
            stats["failure_count"] += 1
            stats["consecutive_failures"] += 1
            self._save()
