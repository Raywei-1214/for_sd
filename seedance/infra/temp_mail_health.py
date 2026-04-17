import json
import math
from pathlib import Path

from seedance.core.logger import get_logger

logger = get_logger()
HIGH_RISK_FAILURE_RATE_THRESHOLD = 0.30
HIGH_RISK_CREDITS_70_RATE_THRESHOLD = 0.60


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
        provider_stats = providers.setdefault(provider_name, {})

        # ================================
        # 兼容旧版健康文件
        # 目的: 在不清空历史数据的前提下补齐新的统计字段
        # 边界: 调度仍只依赖 success/failure/consecutive_failures，不改变旧策略
        # ================================
        success_count = int(provider_stats.get("success_count", 0) or 0)
        failure_count = int(provider_stats.get("failure_count", 0) or 0)
        total_failure_count = int(provider_stats.get("total_failure_count", failure_count) or 0)
        attempt_count = int(
            provider_stats.get("attempt_count", success_count + total_failure_count) or 0
        )
        provider_stats["success_count"] = success_count
        provider_stats["failure_count"] = failure_count
        provider_stats["consecutive_failures"] = int(provider_stats.get("consecutive_failures", 0) or 0)
        provider_stats["total_failure_count"] = total_failure_count
        provider_stats["attempt_count"] = max(attempt_count, success_count + total_failure_count)
        provider_stats["available_count"] = int(provider_stats.get("available_count", 0) or 0)
        provider_stats["credits_observed_count"] = int(provider_stats.get("credits_observed_count", 0) or 0)
        provider_stats["credits_70_count"] = int(provider_stats.get("credits_70_count", 0) or 0)
        return provider_stats

    def _health_score(self, provider_name: str) -> float:
        stats = self._get_provider_stats(provider_name)
        success_count = stats["success_count"]
        failure_count = stats["failure_count"]
        consecutive_failures = stats["consecutive_failures"]

        success_rate = (success_count + 1) / (success_count + failure_count + 2)
        penalty = min(consecutive_failures * 0.08, 0.32)
        return max(success_rate - penalty, 0.05)

    def build_provider_plan(
        self,
        provider_names: list[str],
        total_count: int,
        provider_ratios: dict[str, int] | None = None,
    ) -> list[str]:
        if not provider_names or total_count <= 0:
            return []

        if provider_ratios:
            return self._build_ratio_provider_plan(provider_names, total_count, provider_ratios)

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

    def _build_ratio_provider_plan(
        self,
        provider_names: list[str],
        total_count: int,
        provider_ratios: dict[str, int],
    ) -> list[str]:
        active_provider_names = [
            provider_name
            for provider_name in provider_names
            if provider_ratios.get(provider_name, 0) > 0
        ]
        if not active_provider_names:
            return []

        raw_counts = {
            provider_name: total_count * provider_ratios.get(provider_name, 0) / 100
            for provider_name in active_provider_names
        }
        assigned_counts = {
            provider_name: math.floor(raw_count)
            for provider_name, raw_count in raw_counts.items()
        }
        remaining_slots = total_count - sum(assigned_counts.values())

        fractional_rank = sorted(
            active_provider_names,
            key=lambda provider_name: (
                raw_counts[provider_name] - assigned_counts[provider_name],
                provider_ratios.get(provider_name, 0),
            ),
            reverse=True,
        )
        for provider_name in fractional_rank[:remaining_slots]:
            assigned_counts[provider_name] += 1

        rotation_index = self.data.get("rotation_index", 0)
        rotation_offset = rotation_index % len(active_provider_names)
        round_robin_provider_names = (
            active_provider_names[rotation_offset:] + active_provider_names[:rotation_offset]
        )

        plan: list[str] = []
        while len(plan) < total_count:
            appended = False
            for provider_name in round_robin_provider_names:
                if assigned_counts[provider_name] <= 0:
                    continue
                plan.append(provider_name)
                assigned_counts[provider_name] -= 1
                appended = True
                if len(plan) >= total_count:
                    break
            if not appended:
                break

        self.data["rotation_index"] = (rotation_index + total_count) % len(active_provider_names)
        self._save()
        return plan

    def record_provider_result(
        self,
        provider_name: str,
        *,
        success: bool,
        hard_failure: bool,
        available: bool = False,
        credits_observed: bool = False,
        credits_70: bool = False,
    ) -> None:
        stats = self._get_provider_stats(provider_name)
        stats["attempt_count"] += 1

        if success:
            stats["success_count"] += 1
            stats["consecutive_failures"] = 0
            if available:
                stats["available_count"] += 1
        else:
            stats["total_failure_count"] += 1
            if hard_failure:
                stats["failure_count"] += 1
                stats["consecutive_failures"] += 1

        if credits_observed:
            stats["credits_observed_count"] += 1
            if credits_70:
                stats["credits_70_count"] += 1

        self._save()

    def build_provider_risk_snapshot(
        self,
        provider_names: list[str] | None = None,
    ) -> list[dict]:
        return self.build_provider_quality_snapshot(provider_names)

    def build_provider_quality_snapshot(
        self,
        provider_names: list[str] | None = None,
    ) -> list[dict]:
        if provider_names is None:
            provider_names = sorted(self.data.get("providers", {}).keys())

        snapshots: list[dict] = []
        for provider_name in provider_names:
            stats = self._get_provider_stats(provider_name)
            attempt_count = stats["attempt_count"]
            credits_observed_count = stats["credits_observed_count"]
            failure_rate = (
                stats["total_failure_count"] / attempt_count
                if attempt_count
                else 0.0
            )
            available_rate = (
                stats["available_count"] / attempt_count
                if attempt_count
                else 0.0
            )
            credits_70_rate = (
                stats["credits_70_count"] / credits_observed_count
                if credits_observed_count
                else 0.0
            )
            snapshots.append(
                {
                    "provider_name": provider_name,
                    "attempt_count": attempt_count,
                    "success_count": stats["success_count"],
                    "available_count": stats["available_count"],
                    "hard_failure_count": stats["failure_count"],
                    "total_failure_count": stats["total_failure_count"],
                    "credits_observed_count": credits_observed_count,
                    "credits_70_count": stats["credits_70_count"],
                    "failure_rate": failure_rate,
                    "available_rate": available_rate,
                    "credits_70_rate": credits_70_rate,
                }
            )
        return snapshots

    def list_high_risk_providers(
        self,
        provider_names: list[str] | None = None,
    ) -> list[dict]:
        snapshots = self.build_provider_quality_snapshot(provider_names)
        high_risk_providers = [
            snapshot
            for snapshot in snapshots
            if snapshot["failure_rate"] > HIGH_RISK_FAILURE_RATE_THRESHOLD
            or snapshot["credits_70_rate"] > HIGH_RISK_CREDITS_70_RATE_THRESHOLD
        ]
        return sorted(
            high_risk_providers,
            key=lambda snapshot: (
                max(snapshot["failure_rate"], snapshot["credits_70_rate"]),
                snapshot["attempt_count"],
            ),
            reverse=True,
        )
