import csv
import json
from collections import Counter
from pathlib import Path

from seedance.core.logger import get_logger
from seedance.core.models import RegistrationResult
from seedance.core.notion_rules import classify_account_quality, evaluate_notion_sync_eligibility

logger = get_logger()


def build_failure_reason(result: RegistrationResult) -> str:
    failed_step = result.failed_step or "unknown_step"
    error_message = result.error_message or "未记录失败原因"
    return f"{failed_step} | {error_message}"


class RunReportWriter:
    def __init__(self, report_dir: Path):
        self.report_dir = report_dir
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def _is_notion_eligible(self, result: RegistrationResult) -> bool:
        eligible, _ = evaluate_notion_sync_eligibility(result)
        return eligible

    def _fill_account_quality(self, result: RegistrationResult) -> None:
        quality, reason = classify_account_quality(result)
        result.account_quality = quality
        result.account_quality_reason = reason

    def _build_summary(self, results: list[RegistrationResult], script_total_seconds: float) -> dict:
        for result in results:
            self._fill_account_quality(result)

        success_count = sum(1 for result in results if result.success)
        failed_results = [result for result in results if not result.success]
        available_count = sum(
            1
            for result in results
            if self._is_notion_eligible(result)
        )
        notion_written_count = sum(1 for result in results if result.notion_ok)
        notion_skipped_count = sum(1 for result in results if result.notion_skipped)
        notion_failed_count = sum(
            1
            for result in results
            if result.success and not result.notion_ok and not result.notion_skipped
        )
        network_request_count = sum(result.request_count for result in results)
        network_response_count = sum(result.response_count for result in results)
        network_failed_request_count = sum(result.failed_request_count for result in results)
        network_transferred_bytes = sum(result.transferred_bytes for result in results)
        network_request_type_counter = Counter()
        for result in results:
            network_request_type_counter.update(result.request_type_counts or {})
        account_quality_counter = Counter(result.account_quality or "unknown" for result in results)
        failure_counter = Counter(
            build_failure_reason(result)
            for result in failed_results
        )

        # ================================
        # 汇总报告要同时服务“快速查看”和“程序读取”
        # 因此总览、分类、明细分开保存
        # ================================
        return {
            "total_count": len(results),
            "success_count": success_count,
            "fail_count": len(results) - success_count,
            "available_count": available_count,
            "success_rate": round((success_count / len(results) * 100), 1) if results else 0.0,
            "available_rate": round((available_count / len(results) * 100), 1) if results else 0.0,
            "duration_seconds": round(script_total_seconds, 2),
            "notion_written_count": notion_written_count,
            "notion_skipped_count": notion_skipped_count,
            "notion_failed_count": notion_failed_count,
            "network_request_count": network_request_count,
            "network_response_count": network_response_count,
            "network_failed_request_count": network_failed_request_count,
            "network_transferred_bytes": network_transferred_bytes,
            "network_transferred_megabytes": round(network_transferred_bytes / (1024 * 1024), 2),
            "network_request_type_counts": dict(network_request_type_counter),
            "account_quality_counts": dict(account_quality_counter),
            "failure_breakdown": [
                {"reason": reason, "count": count}
                for reason, count in failure_counter.most_common()
            ],
        }

    def _serialize_result(self, result: RegistrationResult) -> dict:
        return {
            "thread_id": result.thread_id,
            "success": result.success,
            "current_step": result.current_step,
            "failed_step": result.failed_step,
            "email": result.email,
            "provider_name": result.provider_name,
            "sessionid": result.sessionid,
            "credits": result.credits,
            "country": result.country,
            "seedance_value": result.seedance_value,
            "duration_seconds": round(result.duration_seconds, 2),
            "started_at": result.started_at,
            "finished_at": result.finished_at,
            "error_message": result.error_message,
            "failure_context": getattr(result, "failure_context", None),
            "account_quality": result.account_quality,
            "account_quality_reason": result.account_quality_reason,
            "notion_ok": result.notion_ok,
            "notion_skipped": result.notion_skipped,
            "notion_error": result.notion_error,
            "notion_skip_reason": result.notion_skip_reason,
            "backup_ok": result.backup_ok,
            "backup_error": result.backup_error,
            "request_count": result.request_count,
            "response_count": result.response_count,
            "failed_request_count": result.failed_request_count,
            "transferred_bytes": result.transferred_bytes,
            "request_type_counts": json.dumps(result.request_type_counts, ensure_ascii=False),
        }

    def _build_notion_failure_payload(
        self,
        timestamp: str,
        results: list[RegistrationResult],
        script_start_datetime: str,
        script_end_datetime: str,
        script_total_seconds: float,
    ) -> dict:
        notion_failures = []
        for result in results:
            if not result.success:
                continue
            if result.notion_ok or result.notion_skipped:
                continue
            notion_failures.append(
                {
                    "thread_id": result.thread_id,
                    "email": result.email,
                    "password": result.password,
                    "provider_name": result.provider_name,
                    "sessionid": result.sessionid,
                    "credits": result.credits,
                    "country": result.country,
                    "started_at": result.started_at,
                    "finished_at": result.finished_at,
                    "notion_error": result.notion_error,
                    "backup_ok": result.backup_ok,
                    "backup_error": result.backup_error,
                }
            )

        return {
            "timestamp": timestamp,
            "started_at": script_start_datetime,
            "finished_at": script_end_datetime,
            "duration_seconds": round(script_total_seconds, 2),
            "failure_count": len(notion_failures),
            "failures": notion_failures,
        }

    def write(
        self,
        timestamp: str,
        results: list[RegistrationResult],
        script_start_datetime: str,
        script_end_datetime: str,
        script_total_seconds: float,
    ) -> tuple[Path, Path, Path]:
        summary = self._build_summary(results, script_total_seconds)
        json_path = self.report_dir / f"run_report_{timestamp}.json"
        csv_path = self.report_dir / f"run_report_{timestamp}.csv"
        notion_failures_path = self.report_dir / f"notion_failures_{timestamp}.json"

        json_payload = {
            "started_at": script_start_datetime,
            "finished_at": script_end_datetime,
            "duration_seconds": round(script_total_seconds, 2),
            "summary": summary,
            "results": [self._serialize_result(result) for result in results],
        }
        json_path.write_text(
            json.dumps(json_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        notion_failure_payload = self._build_notion_failure_payload(
            timestamp=timestamp,
            results=results,
            script_start_datetime=script_start_datetime,
            script_end_datetime=script_end_datetime,
            script_total_seconds=script_total_seconds,
        )
        notion_failures_path.write_text(
            json.dumps(notion_failure_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "thread_id",
                    "success",
                    "current_step",
                    "failed_step",
                    "email",
                    "provider_name",
                    "sessionid",
                    "credits",
                    "country",
                    "seedance_value",
                    "duration_seconds",
                    "started_at",
                    "finished_at",
                    "error_message",
                    "failure_context",
                    "account_quality",
                    "account_quality_reason",
                    "notion_ok",
                    "notion_skipped",
                    "notion_error",
                    "notion_skip_reason",
                    "backup_ok",
                    "backup_error",
                    "request_count",
                    "response_count",
                    "failed_request_count",
                    "transferred_bytes",
                    "request_type_counts",
                ],
            )
            writer.writeheader()
            for result in results:
                writer.writerow(self._serialize_result(result))

        logger.info(f"运行报告(JSON): {json_path}")
        logger.info(f"运行报告(CSV): {csv_path}")
        logger.info(f"Notion 失败清单(JSON): {notion_failures_path}")
        return json_path, csv_path, notion_failures_path
