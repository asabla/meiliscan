"""Tests for InstanceConfigAnalyzer."""

import pytest

from meiliscan.analyzers.instance_config_analyzer import InstanceConfigAnalyzer
from meiliscan.models.finding import FindingCategory, FindingSeverity
from meiliscan.models.instance_config import (
    IndexingConfig,
    InstanceLaunchConfig,
    SnapshotConfig,
    SSLConfig,
)


@pytest.fixture
def analyzer():
    """Create an InstanceConfigAnalyzer instance."""
    return InstanceConfigAnalyzer()


@pytest.fixture
def production_config():
    """Create a production config for testing."""
    return InstanceLaunchConfig(
        env="production",
        master_key="this-is-a-secure-master-key-32bytes!",
        http_addr="localhost:7700",
        log_level="INFO",
    )


@pytest.fixture
def development_config():
    """Create a development config for testing."""
    return InstanceLaunchConfig(
        env="development",
        http_addr="localhost:7700",
    )


class TestInstanceConfigAnalyzer:
    """Tests for InstanceConfigAnalyzer."""

    def test_analyzer_name(self, analyzer):
        """Test analyzer name property."""
        assert analyzer.name == "instance_config"

    # I001: Production master key tests

    def test_production_without_master_key_i001(self, analyzer):
        """Test detection of production without master key (I001)."""
        config = InstanceLaunchConfig(
            env="production",
            master_key=None,
            http_addr="localhost:7700",
        )

        findings = analyzer.analyze(config)
        i001_findings = [f for f in findings if f.id == "MEILI-I001"]

        assert len(i001_findings) == 1
        assert i001_findings[0].severity == FindingSeverity.CRITICAL
        assert i001_findings[0].category == FindingCategory.INSTANCE_CONFIG
        assert "master key" in i001_findings[0].title.lower()

    def test_production_with_short_master_key_i001(self, analyzer):
        """Test detection of short master key in production (I001)."""
        config = InstanceLaunchConfig(
            env="production",
            master_key="short",  # Only 5 bytes, needs 16+
            http_addr="localhost:7700",
        )

        findings = analyzer.analyze(config)
        i001_findings = [f for f in findings if f.id == "MEILI-I001"]

        assert len(i001_findings) == 1
        assert i001_findings[0].severity == FindingSeverity.CRITICAL
        assert "too short" in i001_findings[0].title.lower()

    def test_production_with_valid_master_key_no_i001(
        self, analyzer, production_config
    ):
        """Test no I001 when master key is valid in production."""
        findings = analyzer.analyze(production_config)
        i001_findings = [f for f in findings if f.id == "MEILI-I001"]

        assert len(i001_findings) == 0

    def test_development_without_master_key_no_i001(self, analyzer, development_config):
        """Test no I001 in development mode without master key."""
        findings = analyzer.analyze(development_config)
        i001_findings = [f for f in findings if f.id == "MEILI-I001"]

        assert len(i001_findings) == 0

    # I002: HTTP binding security tests

    def test_binds_all_interfaces_without_ssl_i002(self, analyzer):
        """Test detection of binding to all interfaces without SSL (I002)."""
        config = InstanceLaunchConfig(
            env="production",
            master_key="secure-master-key-32bytes-long!!",
            http_addr="0.0.0.0:7700",
            ssl=SSLConfig(),  # No SSL configured
        )

        findings = analyzer.analyze(config)
        i002_findings = [f for f in findings if f.id == "MEILI-I002"]

        assert len(i002_findings) == 1
        assert i002_findings[0].severity == FindingSeverity.WARNING
        assert "ssl" in i002_findings[0].title.lower()

    def test_binds_all_interfaces_with_ssl_no_i002(self, analyzer):
        """Test no I002 when SSL is configured."""
        config = InstanceLaunchConfig(
            env="production",
            master_key="secure-master-key-32bytes-long!!",
            http_addr="0.0.0.0:7700",
            ssl=SSLConfig(
                ssl_cert_path="/path/to/cert.pem", ssl_key_path="/path/to/key.pem"
            ),
        )

        findings = analyzer.analyze(config)
        i002_findings = [f for f in findings if f.id == "MEILI-I002"]

        assert len(i002_findings) == 0

    def test_localhost_binding_no_i002(self, analyzer, production_config):
        """Test no I002 when binding to localhost only."""
        findings = analyzer.analyze(production_config)
        i002_findings = [f for f in findings if f.id == "MEILI-I002"]

        assert len(i002_findings) == 0

    def test_development_binds_all_interfaces_suggestion_i002(self, analyzer):
        """Test I002 is suggestion severity in development."""
        config = InstanceLaunchConfig(
            env="development",
            http_addr="0.0.0.0:7700",
        )

        findings = analyzer.analyze(config)
        i002_findings = [f for f in findings if f.id == "MEILI-I002"]

        assert len(i002_findings) == 1
        assert i002_findings[0].severity == FindingSeverity.SUGGESTION

    # I003: Log level tests

    def test_debug_log_level_production_i003(self, analyzer):
        """Test detection of DEBUG log level in production (I003)."""
        config = InstanceLaunchConfig(
            env="production",
            master_key="secure-master-key-32bytes-long!!",
            log_level="DEBUG",
        )

        findings = analyzer.analyze(config)
        i003_findings = [f for f in findings if f.id == "MEILI-I003"]

        assert len(i003_findings) == 1
        assert i003_findings[0].severity == FindingSeverity.SUGGESTION
        assert "verbose" in i003_findings[0].title.lower()

    def test_trace_log_level_production_i003(self, analyzer):
        """Test detection of TRACE log level in production (I003)."""
        config = InstanceLaunchConfig(
            env="production",
            master_key="secure-master-key-32bytes-long!!",
            log_level="TRACE",
        )

        findings = analyzer.analyze(config)
        i003_findings = [f for f in findings if f.id == "MEILI-I003"]

        assert len(i003_findings) == 1
        assert i003_findings[0].severity == FindingSeverity.SUGGESTION

    def test_off_log_level_production_i003(self, analyzer):
        """Test detection of disabled logging in production (I003)."""
        config = InstanceLaunchConfig(
            env="production",
            master_key="secure-master-key-32bytes-long!!",
            log_level="OFF",
        )

        findings = analyzer.analyze(config)
        i003_findings = [f for f in findings if f.id == "MEILI-I003"]

        assert len(i003_findings) == 1
        assert i003_findings[0].severity == FindingSeverity.WARNING
        assert "disabled" in i003_findings[0].title.lower()

    def test_info_log_level_no_i003(self, analyzer, production_config):
        """Test no I003 when log level is INFO in production."""
        findings = analyzer.analyze(production_config)
        i003_findings = [f for f in findings if f.id == "MEILI-I003"]

        assert len(i003_findings) == 0

    def test_debug_log_level_development_no_i003(self, analyzer):
        """Test no I003 for debug logging in development."""
        config = InstanceLaunchConfig(
            env="development",
            log_level="DEBUG",
        )

        findings = analyzer.analyze(config)
        i003_findings = [f for f in findings if f.id == "MEILI-I003"]

        assert len(i003_findings) == 0

    # I004: Snapshot scheduling tests

    def test_no_snapshots_production_i004(self, analyzer):
        """Test detection of no snapshot schedule in production (I004)."""
        config = InstanceLaunchConfig(
            env="production",
            master_key="secure-master-key-32bytes-long!!",
            snapshot=SnapshotConfig(schedule_snapshot=None),
        )

        findings = analyzer.analyze(config)
        i004_findings = [f for f in findings if f.id == "MEILI-I004"]

        assert len(i004_findings) == 1
        assert i004_findings[0].severity == FindingSeverity.SUGGESTION
        assert "snapshot" in i004_findings[0].title.lower()

    def test_snapshots_enabled_no_i004(self, analyzer):
        """Test no I004 when snapshots are scheduled."""
        config = InstanceLaunchConfig(
            env="production",
            master_key="secure-master-key-32bytes-long!!",
            snapshot=SnapshotConfig(schedule_snapshot=86400),  # Daily
        )

        findings = analyzer.analyze(config)
        i004_findings = [f for f in findings if f.id == "MEILI-I004"]

        assert len(i004_findings) == 0

    def test_no_snapshots_development_no_i004(self, analyzer, development_config):
        """Test no I004 for missing snapshots in development."""
        findings = analyzer.analyze(development_config)
        i004_findings = [f for f in findings if f.id == "MEILI-I004"]

        assert len(i004_findings) == 0

    # I005: Payload size tests

    def test_low_payload_size_i005(self, analyzer):
        """Test detection of very low payload size limit (I005)."""
        config = InstanceLaunchConfig(
            env="production",
            master_key="secure-master-key-32bytes-long!!",
            http_payload_size_limit=512 * 1024,  # 512KB - too low
        )

        findings = analyzer.analyze(config)
        i005_findings = [f for f in findings if f.id == "MEILI-I005"]

        assert len(i005_findings) == 1
        assert i005_findings[0].severity == FindingSeverity.WARNING
        assert "low" in i005_findings[0].title.lower()

    def test_high_payload_size_i005(self, analyzer):
        """Test detection of very high payload size limit (I005)."""
        config = InstanceLaunchConfig(
            env="production",
            master_key="secure-master-key-32bytes-long!!",
            http_payload_size_limit=1024 * 1024 * 1024,  # 1GB - too high
        )

        findings = analyzer.analyze(config)
        i005_findings = [f for f in findings if f.id == "MEILI-I005"]

        assert len(i005_findings) == 1
        assert i005_findings[0].severity == FindingSeverity.WARNING
        assert "high" in i005_findings[0].title.lower()

    def test_normal_payload_size_no_i005(self, analyzer, production_config):
        """Test no I005 when payload size is in normal range."""
        findings = analyzer.analyze(production_config)
        i005_findings = [f for f in findings if f.id == "MEILI-I005"]

        assert len(i005_findings) == 0

    # I006: Indexing settings tests

    def test_very_high_indexing_memory_i006(self, analyzer):
        """Test detection of very high indexing memory (I006)."""
        config = InstanceLaunchConfig(
            env="production",
            master_key="secure-master-key-32bytes-long!!",
            indexing=IndexingConfig(max_indexing_memory="128GB"),
        )

        findings = analyzer.analyze(config)
        i006_findings = [f for f in findings if f.id == "MEILI-I006"]

        assert len(i006_findings) >= 1
        high_memory = [f for f in i006_findings if "high" in f.title.lower()]
        assert len(high_memory) == 1

    def test_very_low_indexing_memory_i006(self, analyzer):
        """Test detection of very low indexing memory (I006)."""
        config = InstanceLaunchConfig(
            env="production",
            master_key="secure-master-key-32bytes-long!!",
            indexing=IndexingConfig(max_indexing_memory="128MB"),
        )

        findings = analyzer.analyze(config)
        i006_findings = [f for f in findings if f.id == "MEILI-I006"]

        assert len(i006_findings) >= 1
        low_memory = [f for f in i006_findings if "low" in f.title.lower()]
        assert len(low_memory) == 1

    def test_high_thread_count_i006(self, analyzer):
        """Test detection of high indexing thread count (I006)."""
        config = InstanceLaunchConfig(
            env="production",
            master_key="secure-master-key-32bytes-long!!",
            indexing=IndexingConfig(max_indexing_threads=32),
        )

        findings = analyzer.analyze(config)
        i006_findings = [f for f in findings if f.id == "MEILI-I006"]

        assert len(i006_findings) >= 1
        thread_finding = [f for f in i006_findings if "thread" in f.title.lower()]
        assert len(thread_finding) == 1

    def test_normal_indexing_settings_no_i006(self, analyzer, production_config):
        """Test no I006 when indexing settings are not set (defaults)."""
        findings = analyzer.analyze(production_config)
        i006_findings = [f for f in findings if f.id == "MEILI-I006"]

        assert len(i006_findings) == 0

    # Multiple findings tests

    def test_multiple_findings_combined(self, analyzer):
        """Test that multiple issues produce multiple findings."""
        config = InstanceLaunchConfig(
            env="production",
            master_key=None,  # I001
            http_addr="0.0.0.0:7700",  # I002
            log_level="DEBUG",  # I003
            snapshot=SnapshotConfig(schedule_snapshot=None),  # I004
            http_payload_size_limit=100,  # I005
        )

        findings = analyzer.analyze(config)

        assert len(findings) >= 5
        finding_ids = {f.id for f in findings}
        assert "MEILI-I001" in finding_ids
        assert "MEILI-I002" in finding_ids
        assert "MEILI-I003" in finding_ids
        assert "MEILI-I004" in finding_ids
        assert "MEILI-I005" in finding_ids

    def test_well_configured_production_minimal_findings(self, analyzer):
        """Test that a well-configured production instance has minimal findings."""
        config = InstanceLaunchConfig(
            env="production",
            master_key="very-secure-master-key-at-least-32-bytes",
            http_addr="127.0.0.1:7700",
            log_level="INFO",
            snapshot=SnapshotConfig(schedule_snapshot=86400),
            http_payload_size_limit=104857600,  # 100MB default
        )

        findings = analyzer.analyze(config)

        # Should have no critical/warning findings
        critical_warnings = [
            f
            for f in findings
            if f.severity in (FindingSeverity.CRITICAL, FindingSeverity.WARNING)
        ]
        assert len(critical_warnings) == 0


class TestInstanceLaunchConfigModel:
    """Tests for InstanceLaunchConfig model."""

    def test_is_production_true(self):
        """Test is_production returns True for production env."""
        config = InstanceLaunchConfig(env="production")
        assert config.is_production is True

    def test_is_production_false(self):
        """Test is_production returns False for development env."""
        config = InstanceLaunchConfig(env="development")
        assert config.is_production is False

    def test_is_production_case_insensitive(self):
        """Test is_production is case-insensitive."""
        config = InstanceLaunchConfig(env="PRODUCTION")
        assert config.is_production is True

    def test_binds_to_all_interfaces_true(self):
        """Test binds_to_all_interfaces for 0.0.0.0."""
        config = InstanceLaunchConfig(http_addr="0.0.0.0:7700")
        assert config.binds_to_all_interfaces is True

    def test_binds_to_all_interfaces_false(self):
        """Test binds_to_all_interfaces for localhost."""
        config = InstanceLaunchConfig(http_addr="localhost:7700")
        assert config.binds_to_all_interfaces is False


class TestIndexingConfig:
    """Tests for IndexingConfig memory parsing."""

    def test_get_memory_bytes_gb(self):
        """Test parsing GB memory value."""
        config = IndexingConfig(max_indexing_memory="8GB")
        assert config.get_memory_bytes() == 8 * 1024**3

    def test_get_memory_bytes_mb(self):
        """Test parsing MB memory value."""
        config = IndexingConfig(max_indexing_memory="512MB")
        assert config.get_memory_bytes() == 512 * 1024**2

    def test_get_memory_bytes_int(self):
        """Test parsing integer bytes value."""
        config = IndexingConfig(max_indexing_memory=1073741824)  # 1GB
        assert config.get_memory_bytes() == 1073741824

    def test_get_memory_bytes_none(self):
        """Test None when not set."""
        config = IndexingConfig(max_indexing_memory=None)
        assert config.get_memory_bytes() is None

    def test_get_memory_bytes_gib(self):
        """Test parsing GiB (binary) memory value."""
        config = IndexingConfig(max_indexing_memory="4GiB")
        assert config.get_memory_bytes() == 4 * 1024**3


class TestSSLConfig:
    """Tests for SSLConfig."""

    def test_is_configured_with_cert(self):
        """Test is_configured with cert path."""
        config = SSLConfig(ssl_cert_path="/path/to/cert.pem")
        assert config.is_configured is True

    def test_is_configured_with_key(self):
        """Test is_configured with key path."""
        config = SSLConfig(ssl_key_path="/path/to/key.pem")
        assert config.is_configured is True

    def test_is_configured_false(self):
        """Test is_configured when not configured."""
        config = SSLConfig()
        assert config.is_configured is False


class TestSnapshotConfig:
    """Tests for SnapshotConfig."""

    def test_is_scheduled_with_seconds(self):
        """Test is_scheduled with seconds value."""
        config = SnapshotConfig(schedule_snapshot=86400)
        assert config.is_scheduled is True

    def test_is_scheduled_with_true(self):
        """Test is_scheduled with boolean True."""
        config = SnapshotConfig(schedule_snapshot=True)
        assert config.is_scheduled is True

    def test_is_scheduled_with_false(self):
        """Test is_scheduled with boolean False."""
        config = SnapshotConfig(schedule_snapshot=False)
        assert config.is_scheduled is False

    def test_is_scheduled_with_none(self):
        """Test is_scheduled with None."""
        config = SnapshotConfig(schedule_snapshot=None)
        assert config.is_scheduled is False

    def test_is_scheduled_with_zero(self):
        """Test is_scheduled with zero."""
        config = SnapshotConfig(schedule_snapshot=0)
        assert config.is_scheduled is False
