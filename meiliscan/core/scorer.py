"""Health scorer for calculating overall health scores."""

from meiliscan.models.finding import Finding, FindingSeverity
from meiliscan.models.report import AnalysisReport


class HealthScorer:
    """Calculate health scores based on findings."""

    # Severity weights for score calculation
    SEVERITY_WEIGHTS = {
        FindingSeverity.CRITICAL: 15,
        FindingSeverity.WARNING: 8,
        FindingSeverity.SUGGESTION: 3,
        FindingSeverity.INFO: 0,
    }

    def __init__(self, max_score: int = 100):
        """Initialize the scorer.

        Args:
            max_score: Maximum possible score
        """
        self.max_score = max_score

    def calculate_score(self, findings: list[Finding]) -> int:
        """Calculate health score based on findings.

        Args:
            findings: List of findings to score

        Returns:
            Health score from 0 to max_score
        """
        if not findings:
            return self.max_score

        total_penalty = sum(self.SEVERITY_WEIGHTS.get(f.severity, 0) for f in findings)

        score = max(0, self.max_score - total_penalty)
        return score

    def score_report(self, report: AnalysisReport) -> int:
        """Calculate and set the health score for a report.

        Args:
            report: The analysis report to score

        Returns:
            The calculated health score
        """
        all_findings = report.get_all_findings()
        score = self.calculate_score(all_findings)
        report.summary.health_score = score
        return score

    def get_score_label(self, score: int) -> str:
        """Get a human-readable label for a score.

        Args:
            score: The health score

        Returns:
            Label describing the score
        """
        if score >= 90:
            return "Excellent"
        elif score >= 75:
            return "Good"
        elif score >= 50:
            return "Needs Attention"
        elif score >= 25:
            return "Poor"
        else:
            return "Critical"

    def get_score_breakdown(self, findings: list[Finding]) -> dict:
        """Get a detailed breakdown of score calculation.

        Args:
            findings: List of findings to analyze

        Returns:
            Dictionary with breakdown details including counts, penalties, and totals
        """
        counts = {
            "critical": 0,
            "warning": 0,
            "suggestion": 0,
            "info": 0,
        }
        penalties = {
            "critical": 0,
            "warning": 0,
            "suggestion": 0,
            "info": 0,
        }

        for finding in findings:
            severity_key = finding.severity.value.lower()
            if severity_key in counts:
                counts[severity_key] += 1
                penalties[severity_key] += self.SEVERITY_WEIGHTS.get(
                    finding.severity, 0
                )

        total_penalty = sum(penalties.values())
        score = max(0, self.max_score - total_penalty)

        return {
            "max_score": self.max_score,
            "counts": counts,
            "penalties": penalties,
            "weights": {
                "critical": self.SEVERITY_WEIGHTS[FindingSeverity.CRITICAL],
                "warning": self.SEVERITY_WEIGHTS[FindingSeverity.WARNING],
                "suggestion": self.SEVERITY_WEIGHTS[FindingSeverity.SUGGESTION],
                "info": self.SEVERITY_WEIGHTS[FindingSeverity.INFO],
            },
            "total_penalty": total_penalty,
            "final_score": score,
            "label": self.get_score_label(score),
            "capped": total_penalty > self.max_score,
        }
