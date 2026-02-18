"""Tests for the in-memory MetricsRegistry (counters and histograms)."""

import pytest

from investigator.observability.metrics import Counter, Histogram, MetricsRegistry


class TestCounter:
    def test_starts_at_zero(self):
        c = Counter("test_total")
        assert c.value() == 0

    def test_increment_by_one(self):
        c = Counter("test_total")
        c.inc()
        assert c.value() == 1

    def test_increment_multiple(self):
        c = Counter("test_total")
        c.inc()
        c.inc()
        c.inc()
        assert c.value() == 3

    def test_increment_with_amount(self):
        c = Counter("test_total")
        c.inc(5)
        assert c.value() == 5

    def test_labeled_counter_separate_buckets(self):
        c = Counter("events_total")
        c.inc(labels={"type": "schema_mismatch"})
        c.inc(labels={"type": "timeout"})
        c.inc(labels={"type": "schema_mismatch"})
        assert c.value(labels={"type": "schema_mismatch"}) == 2
        assert c.value(labels={"type": "timeout"}) == 1

    def test_snapshot_returns_all_series(self):
        c = Counter("events_total")
        c.inc(labels={"env": "prod"})
        c.inc(labels={"env": "dev"})
        snap = c.snapshot()
        assert len(snap) == 2


class TestHistogram:
    def test_starts_empty(self):
        h = Histogram("duration_ms")
        assert h.count() == 0

    def test_observe_increments_count(self):
        h = Histogram("duration_ms")
        h.observe(42.5)
        assert h.count() == 1

    def test_mean_single_value(self):
        h = Histogram("duration_ms")
        h.observe(100.0)
        assert h.mean() == pytest.approx(100.0)

    def test_mean_multiple_values(self):
        h = Histogram("duration_ms")
        h.observe(10.0)
        h.observe(20.0)
        h.observe(30.0)
        assert h.mean() == pytest.approx(20.0)

    def test_p50_approximate(self):
        h = Histogram("duration_ms")
        for v in range(1, 101):
            h.observe(float(v))
        p50 = h.percentile(50)
        assert 45.0 <= p50 <= 55.0

    def test_snapshot(self):
        h = Histogram("duration_ms")
        h.observe(10.0)
        h.observe(20.0)
        snap = h.snapshot()
        assert snap["count"] == 2
        assert "mean" in snap
        assert "p50" in snap
        assert "p95" in snap


class TestMetricsRegistry:
    def setup_method(self):
        self.reg = MetricsRegistry()

    def test_counter_creates_on_first_access(self):
        c = self.reg.counter("pipeline_runs_total")
        assert isinstance(c, Counter)

    def test_same_name_returns_same_counter(self):
        c1 = self.reg.counter("pipeline_runs_total")
        c2 = self.reg.counter("pipeline_runs_total")
        assert c1 is c2

    def test_histogram_creates_on_first_access(self):
        h = self.reg.histogram("step_duration_ms")
        assert isinstance(h, Histogram)

    def test_snapshot_returns_all_metrics(self):
        self.reg.counter("runs_total").inc()
        self.reg.histogram("duration_ms").observe(50.0)
        snap = self.reg.snapshot()
        assert "counters" in snap
        assert "histograms" in snap

    def test_snapshot_counters_present(self):
        self.reg.counter("incidents_total").inc()
        snap = self.reg.snapshot()
        assert "incidents_total" in snap["counters"]

    def test_snapshot_histograms_present(self):
        self.reg.histogram("pipeline_ms").observe(100.0)
        snap = self.reg.snapshot()
        assert "pipeline_ms" in snap["histograms"]

    def test_pipeline_run_metrics_recorded(self, pipeline, repo):
        """End-to-end: running the pipeline records metrics in an attached registry."""
        from tests.test_workflow.conftest import make_event
        reg = MetricsRegistry()
        event = make_event(environment="dev")
        repo.create_incident(event)
        pipeline.run(incident_id=event.incident_id, metrics=reg)
        snap = reg.snapshot()
        assert snap["counters"]["pipeline_runs_total"][()]["value"] >= 1

    def test_pipeline_step_durations_recorded(self, pipeline, repo):
        from tests.test_workflow.conftest import make_event
        reg = MetricsRegistry()
        event = make_event(environment="dev")
        repo.create_incident(event)
        pipeline.run(incident_id=event.incident_id, metrics=reg)
        snap = reg.snapshot()
        assert snap["histograms"]["pipeline_step_duration_ms"]["count"] >= 5
