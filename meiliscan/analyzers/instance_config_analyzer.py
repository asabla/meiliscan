"""Instance configuration analyzer for launch-time settings."""

from meiliscan.models.finding import (
    Finding,
    FindingCategory,
    FindingSeverity,
)
from meiliscan.models.instance_config import InstanceLaunchConfig


class InstanceConfigAnalyzer:
    """Analyzer for instance launch configuration (config.toml)."""

    # Minimum recommended master key length (bytes)
    MIN_MASTER_KEY_LENGTH = 16

    # Payload size thresholds
    MIN_PAYLOAD_SIZE = 1024 * 1024  # 1MB
    MAX_PAYLOAD_SIZE = 500 * 1024 * 1024  # 500MB

    @property
    def name(self) -> str:
        return "instance_config"

    def analyze(self, config: InstanceLaunchConfig) -> list[Finding]:
        """Analyze instance launch configuration.

        Args:
            config: Parsed instance launch configuration

        Returns:
            List of findings
        """
        findings: list[Finding] = []

        findings.extend(self._check_production_master_key(config))
        findings.extend(self._check_http_binding_security(config))
        findings.extend(self._check_log_level_production(config))
        findings.extend(self._check_snapshot_scheduling(config))
        findings.extend(self._check_payload_size_limits(config))
        findings.extend(self._check_indexing_settings(config))

        return findings

    def _check_production_master_key(
        self, config: InstanceLaunchConfig
    ) -> list[Finding]:
        """Check master key configuration in production (I001)."""
        findings: list[Finding] = []

        if not config.is_production:
            return findings

        # I001: Production without proper master key
        if config.master_key is None:
            findings.append(
                Finding(
                    id="MEILI-I001",
                    category=FindingCategory.INSTANCE_CONFIG,
                    severity=FindingSeverity.CRITICAL,
                    title="Production environment without master key",
                    description=(
                        "The instance is configured with env=production but no master_key "
                        "is set. In production, all API routes (except /health) should be "
                        "protected by authentication. Without a master key, your data and "
                        "configuration are publicly accessible."
                    ),
                    impact="Complete lack of authentication; anyone can read/modify data",
                    current_value={"env": config.env, "master_key": None},
                    recommended_value={
                        "master_key": "<secure random string of at least 16 bytes>"
                    },
                    references=[
                        "https://www.meilisearch.com/docs/learn/security/basic_security",
                        "https://www.meilisearch.com/docs/learn/self_hosted/configure_meilisearch_at_launch#master-key",
                    ],
                )
            )
        elif len(config.master_key) < self.MIN_MASTER_KEY_LENGTH:
            findings.append(
                Finding(
                    id="MEILI-I001",
                    category=FindingCategory.INSTANCE_CONFIG,
                    severity=FindingSeverity.CRITICAL,
                    title="Master key too short for production",
                    description=(
                        f"The master key is only {len(config.master_key)} bytes, but "
                        f"Meilisearch requires at least {self.MIN_MASTER_KEY_LENGTH} bytes "
                        "for production environments. A short master key is easier to brute-force."
                    ),
                    impact="Weak authentication; master key may be guessable",
                    current_value={
                        "master_key_length": len(config.master_key),
                        "required_length": self.MIN_MASTER_KEY_LENGTH,
                    },
                    recommended_value={
                        "master_key": "<secure random string of at least 16 bytes>"
                    },
                    references=[
                        "https://www.meilisearch.com/docs/learn/security/basic_security",
                    ],
                )
            )

        return findings

    def _check_http_binding_security(
        self, config: InstanceLaunchConfig
    ) -> list[Finding]:
        """Check HTTP binding and SSL configuration (I002)."""
        findings: list[Finding] = []

        # I002: Binding to all interfaces without SSL
        if config.binds_to_all_interfaces and not config.ssl.is_configured:
            severity = (
                FindingSeverity.WARNING
                if config.is_production
                else FindingSeverity.SUGGESTION
            )
            findings.append(
                Finding(
                    id="MEILI-I002",
                    category=FindingCategory.INSTANCE_CONFIG,
                    severity=severity,
                    title="Binding to all interfaces without SSL",
                    description=(
                        f"The instance binds to {config.http_addr} (all network interfaces) "
                        "but SSL is not configured. This means traffic is unencrypted and "
                        "potentially visible to anyone on the network path. Consider enabling "
                        "SSL or using a reverse proxy with TLS termination."
                    ),
                    impact="Unencrypted network traffic; credentials and data exposed",
                    current_value={
                        "http_addr": config.http_addr,
                        "ssl_configured": config.ssl.is_configured,
                    },
                    recommended_value={
                        "option_a": "Configure SSL with ssl_cert_path and ssl_key_path",
                        "option_b": "Use a reverse proxy (nginx/caddy) with TLS termination",
                        "option_c": "Bind to localhost only if not needed externally",
                    },
                    references=[
                        "https://www.meilisearch.com/docs/learn/self_hosted/configure_meilisearch_at_launch#ssl-options",
                    ],
                )
            )

        return findings

    def _check_log_level_production(
        self, config: InstanceLaunchConfig
    ) -> list[Finding]:
        """Check log level appropriateness for production (I003)."""
        findings: list[Finding] = []

        if not config.is_production:
            return findings

        verbose_levels = {"DEBUG", "TRACE"}
        log_level_upper = config.log_level.upper()

        # I003: Verbose logging in production
        if log_level_upper in verbose_levels:
            findings.append(
                Finding(
                    id="MEILI-I003",
                    category=FindingCategory.INSTANCE_CONFIG,
                    severity=FindingSeverity.SUGGESTION,
                    title="Verbose logging enabled in production",
                    description=(
                        f"Log level is set to '{config.log_level}' in production. "
                        "DEBUG and TRACE levels generate excessive log output, which can "
                        "impact performance and fill up disk space quickly. Consider using "
                        "INFO or WARN for production workloads."
                    ),
                    impact="Performance overhead, excessive disk usage, potential sensitive data in logs",
                    current_value={"log_level": config.log_level, "env": config.env},
                    recommended_value={"log_level": "INFO"},
                    references=[
                        "https://www.meilisearch.com/docs/learn/self_hosted/configure_meilisearch_at_launch#log-level",
                    ],
                )
            )

        # Also warn if logging is completely disabled
        if log_level_upper == "OFF":
            findings.append(
                Finding(
                    id="MEILI-I003",
                    category=FindingCategory.INSTANCE_CONFIG,
                    severity=FindingSeverity.WARNING,
                    title="Logging disabled in production",
                    description=(
                        "Log level is set to 'OFF' in production. This means no logs will "
                        "be generated, making it very difficult to diagnose issues or "
                        "detect security incidents."
                    ),
                    impact="No visibility into instance behavior; harder to debug issues",
                    current_value={"log_level": config.log_level},
                    recommended_value={"log_level": "INFO"},
                    references=[
                        "https://www.meilisearch.com/docs/learn/self_hosted/configure_meilisearch_at_launch#log-level",
                    ],
                )
            )

        return findings

    def _check_snapshot_scheduling(self, config: InstanceLaunchConfig) -> list[Finding]:
        """Check snapshot scheduling in production (I004)."""
        findings: list[Finding] = []

        if not config.is_production:
            return findings

        # I004: No snapshots scheduled in production
        if not config.snapshot.is_scheduled:
            findings.append(
                Finding(
                    id="MEILI-I004",
                    category=FindingCategory.INSTANCE_CONFIG,
                    severity=FindingSeverity.SUGGESTION,
                    title="No scheduled snapshots in production",
                    description=(
                        "No snapshot schedule is configured. Snapshots provide a way to "
                        "quickly restore your Meilisearch data in case of failure. For "
                        "production workloads, consider enabling scheduled snapshots as "
                        "part of your backup strategy."
                    ),
                    impact="No automated backups; longer recovery time after failures",
                    current_value={
                        "schedule_snapshot": config.snapshot.schedule_snapshot,
                    },
                    recommended_value={
                        "schedule_snapshot": 86400,  # Daily
                        "snapshot_dir": "/path/to/persistent/storage/snapshots/",
                    },
                    references=[
                        "https://www.meilisearch.com/docs/learn/data_backup/snapshots",
                        "https://www.meilisearch.com/docs/learn/self_hosted/configure_meilisearch_at_launch#schedule-snapshot-creation",
                    ],
                )
            )

        return findings

    def _check_payload_size_limits(self, config: InstanceLaunchConfig) -> list[Finding]:
        """Check HTTP payload size limit configuration (I005)."""
        findings: list[Finding] = []

        payload_size = config.http_payload_size_limit

        # I005: Payload size too low
        if payload_size < self.MIN_PAYLOAD_SIZE:
            findings.append(
                Finding(
                    id="MEILI-I005",
                    category=FindingCategory.INSTANCE_CONFIG,
                    severity=FindingSeverity.WARNING,
                    title="HTTP payload size limit very low",
                    description=(
                        f"http_payload_size_limit is set to {payload_size} bytes "
                        f"({payload_size / 1024 / 1024:.2f} MB). This is very low and may "
                        "cause document ingestion to fail for normal-sized batches. "
                        "The default is ~100MB."
                    ),
                    impact="Document ingestion may fail; forced to use very small batches",
                    current_value={
                        "http_payload_size_limit": payload_size,
                        "in_mb": round(payload_size / 1024 / 1024, 2),
                    },
                    recommended_value={
                        "http_payload_size_limit": 104857600,
                        "in_mb": 100,
                    },
                    references=[
                        "https://www.meilisearch.com/docs/learn/self_hosted/configure_meilisearch_at_launch#payload-limit-size",
                    ],
                )
            )

        # I005: Payload size very high
        if payload_size > self.MAX_PAYLOAD_SIZE:
            findings.append(
                Finding(
                    id="MEILI-I005",
                    category=FindingCategory.INSTANCE_CONFIG,
                    severity=FindingSeverity.WARNING,
                    title="HTTP payload size limit very high",
                    description=(
                        f"http_payload_size_limit is set to {payload_size} bytes "
                        f"({payload_size / 1024 / 1024:.0f} MB). Very large payloads can "
                        "cause memory spikes and may allow denial-of-service attacks if "
                        "the endpoint is exposed. Consider whether such large payloads "
                        "are actually needed."
                    ),
                    impact="Potential memory exhaustion; DoS risk",
                    current_value={
                        "http_payload_size_limit": payload_size,
                        "in_mb": round(payload_size / 1024 / 1024, 0),
                    },
                    recommended_value={
                        "http_payload_size_limit": 104857600,
                        "in_mb": 100,
                    },
                    references=[
                        "https://www.meilisearch.com/docs/learn/self_hosted/configure_meilisearch_at_launch#payload-limit-size",
                    ],
                )
            )

        return findings

    def _check_indexing_settings(self, config: InstanceLaunchConfig) -> list[Finding]:
        """Check indexing memory/threads configuration (I006)."""
        findings: list[Finding] = []

        indexing = config.indexing

        # I006: Potentially risky indexing memory setting
        memory_bytes = indexing.get_memory_bytes()
        if memory_bytes is not None:
            # Very high memory setting (> 64GB) - warn about potential issues
            if memory_bytes > 64 * 1024**3:
                findings.append(
                    Finding(
                        id="MEILI-I006",
                        category=FindingCategory.INSTANCE_CONFIG,
                        severity=FindingSeverity.SUGGESTION,
                        title="Very high indexing memory limit",
                        description=(
                            f"max_indexing_memory is set to {memory_bytes / 1024**3:.1f} GB. "
                            "While this may be intentional for large datasets, ensure your "
                            "system has sufficient RAM. Setting this higher than available "
                            "memory can cause the instance to crash or be killed by the OS."
                        ),
                        impact="Potential OOM crashes if system memory is insufficient",
                        current_value={
                            "max_indexing_memory": indexing.max_indexing_memory,
                            "in_gb": round(memory_bytes / 1024**3, 1),
                        },
                        references=[
                            "https://www.meilisearch.com/docs/learn/self_hosted/configure_meilisearch_at_launch#max-indexing-memory",
                        ],
                    )
                )

            # Very low memory setting (< 256MB) - warn about potential slowness
            if memory_bytes < 256 * 1024**2:
                findings.append(
                    Finding(
                        id="MEILI-I006",
                        category=FindingCategory.INSTANCE_CONFIG,
                        severity=FindingSeverity.SUGGESTION,
                        title="Very low indexing memory limit",
                        description=(
                            f"max_indexing_memory is set to {memory_bytes / 1024**2:.0f} MB. "
                            "This is quite low and may significantly slow down indexing "
                            "operations, especially for larger documents or batches."
                        ),
                        impact="Slower indexing performance",
                        current_value={
                            "max_indexing_memory": indexing.max_indexing_memory,
                            "in_mb": round(memory_bytes / 1024**2, 0),
                        },
                        references=[
                            "https://www.meilisearch.com/docs/learn/self_hosted/configure_meilisearch_at_launch#max-indexing-memory",
                        ],
                    )
                )

        # I006: High indexing threads
        if indexing.max_indexing_threads is not None:
            # Warn if setting appears to use all cores (we can't know actual core count,
            # but we can flag very high values as potentially problematic)
            if indexing.max_indexing_threads > 16:
                findings.append(
                    Finding(
                        id="MEILI-I006",
                        category=FindingCategory.INSTANCE_CONFIG,
                        severity=FindingSeverity.INFO,
                        title="High indexing thread count configured",
                        description=(
                            f"max_indexing_threads is set to {indexing.max_indexing_threads}. "
                            "Using many threads for indexing can speed up document ingestion "
                            "but may impact search latency during indexing. Meilisearch "
                            "recommends using at most half of available cores."
                        ),
                        impact="May impact search latency during heavy indexing",
                        current_value={
                            "max_indexing_threads": indexing.max_indexing_threads,
                        },
                        references=[
                            "https://www.meilisearch.com/docs/learn/self_hosted/configure_meilisearch_at_launch#max-indexing-threads",
                        ],
                    )
                )

        return findings
