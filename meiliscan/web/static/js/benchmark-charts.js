/**
 * Benchmark chart helpers for Meiliscan.
 * Provides dark-theme defaults and chart factory functions using Chart.js.
 */

const BenchmarkCharts = (function () {
    // Color palette matching the app's CSS variables
    const colors = {
        green: 'rgb(34, 197, 94)',
        greenBg: 'rgba(34, 197, 94, 0.6)',
        yellow: 'rgb(251, 191, 36)',
        yellowBg: 'rgba(251, 191, 36, 0.6)',
        red: 'rgb(239, 68, 68)',
        redBg: 'rgba(239, 68, 68, 0.6)',
        blue: 'rgb(59, 130, 246)',
        blueBg: 'rgba(59, 130, 246, 0.6)',
        purple: 'rgb(168, 85, 247)',
        purpleBg: 'rgba(168, 85, 247, 0.6)',
        cyan: 'rgb(6, 182, 212)',
        cyanBg: 'rgba(6, 182, 212, 0.6)',
        gray: 'rgb(148, 163, 184)',
        grayBg: 'rgba(148, 163, 184, 0.4)',
        textPrimary: 'rgb(226, 232, 240)',
        textSecondary: 'rgb(148, 163, 184)',
        gridColor: 'rgba(148, 163, 184, 0.15)',
        borderColor: 'rgba(148, 163, 184, 0.2)',
    };

    // Color per query type
    const queryTypeColors = {
        baseline: colors.grayBg,
        text: colors.blueBg,
        filtered: colors.greenBg,
        sorted: colors.purpleBg,
        faceted: colors.cyanBg,
        complex: colors.yellowBg,
    };

    const queryTypeBorders = {
        baseline: colors.gray,
        text: colors.blue,
        filtered: colors.green,
        sorted: colors.purple,
        faceted: colors.cyan,
        complex: colors.yellow,
    };

    // Latency threshold coloring
    function latencyColor(ms) {
        if (ms < 20) return colors.greenBg;
        if (ms < 50) return colors.yellowBg;
        return colors.redBg;
    }

    function latencyBorder(ms) {
        if (ms < 20) return colors.green;
        if (ms < 50) return colors.yellow;
        return colors.red;
    }

    // Shared chart defaults for dark theme
    Chart.defaults.color = colors.textSecondary;
    Chart.defaults.borderColor = colors.gridColor;
    Chart.defaults.font.family = "'SF Mono', 'Fira Code', 'Cascadia Code', monospace";
    Chart.defaults.font.size = 11;

    /**
     * Chart 1: Latency by Query Type
     * Vertical bar chart showing latency per query type, optionally grouped by index.
     */
    function createQueryTypeChart(canvasId, indexes) {
        var canvas = document.getElementById(canvasId);
        if (!canvas) return null;

        var queryTypes = ['baseline', 'text', 'filtered', 'sorted', 'faceted', 'complex'];
        var labels = queryTypes.map(function (t) {
            return t.charAt(0).toUpperCase() + t.slice(1);
        });

        var datasets;
        if (indexes.length === 1) {
            // Single index: one bar per type, colored by latency
            var idx = indexes[0];
            var data = queryTypes.map(function (t) {
                return idx[t + '_latency_ms'];
            });
            datasets = [{
                label: idx.index_uid,
                data: data,
                backgroundColor: data.map(function (v) {
                    return v !== null ? latencyColor(v) : colors.grayBg;
                }),
                borderColor: data.map(function (v) {
                    return v !== null ? latencyBorder(v) : colors.gray;
                }),
                borderWidth: 1,
                borderRadius: 3,
            }];
        } else {
            // Multiple indexes: show aggregate (average across all indexes per type)
            var avgData = queryTypes.map(function (type) {
                var values = indexes
                    .map(function (idx) { return idx[type + '_latency_ms']; })
                    .filter(function (v) { return v !== null && v !== undefined; });
                if (values.length === 0) return null;
                return values.reduce(function (a, b) { return a + b; }, 0) / values.length;
            });
            datasets = [{
                label: 'Avg across ' + indexes.length + ' indexes',
                data: avgData,
                backgroundColor: avgData.map(function (v) {
                    return v !== null ? latencyColor(v) : colors.grayBg;
                }),
                borderColor: avgData.map(function (v) {
                    return v !== null ? latencyBorder(v) : colors.gray;
                }),
                borderWidth: 1,
                borderRadius: 3,
            }];
        }

        return new Chart(canvas, {
            type: 'bar',
            data: { labels: labels, datasets: datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: indexes.length > 1 },
                    tooltip: {
                        callbacks: {
                            label: function (ctx) {
                                if (ctx.parsed.y === null) return ctx.dataset.label + ': N/A';
                                return ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(1) + 'ms';
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        title: { display: true, text: 'Latency (ms)' },
                        grid: { color: colors.gridColor },
                    },
                    x: {
                        grid: { display: false },
                    }
                }
            }
        });
    }

    /**
     * Chart 2: Percentile Distribution
     * Vertical bar chart showing min, p50, p95, p99, max.
     */
    function createPercentileChart(canvasId, report) {
        var canvas = document.getElementById(canvasId);
        if (!canvas) return null;

        var labels = ['Min', 'P50', 'P95', 'P99', 'Max'];
        var data = [
            report.min_latency_ms,
            report.p50_latency_ms,
            report.p95_latency_ms,
            report.p99_latency_ms,
            report.max_latency_ms,
        ];
        var bgColors = [
            colors.greenBg,
            colors.blueBg,
            colors.yellowBg,
            colors.redBg,
            'rgba(239, 68, 68, 0.8)',
        ];
        var borderColors = [
            colors.green,
            colors.blue,
            colors.yellow,
            colors.red,
            colors.red,
        ];

        return new Chart(canvas, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Latency',
                    data: data,
                    backgroundColor: bgColors,
                    borderColor: borderColors,
                    borderWidth: 1,
                    borderRadius: 3,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function (ctx) {
                                return ctx.parsed.y.toFixed(1) + 'ms';
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        title: { display: true, text: 'Latency (ms)' },
                        grid: { color: colors.gridColor },
                    },
                    x: {
                        grid: { display: false },
                    }
                }
            }
        });
    }

    /**
     * Chart 3: Index Latency Comparison
     * Horizontal bar chart sorted by avg latency descending, top 15.
     */
    function createIndexComparisonChart(canvasId, indexes) {
        var canvas = document.getElementById(canvasId);
        if (!canvas) return null;

        // Sort by avg latency descending, take top 15
        var sorted = indexes.slice().sort(function (a, b) {
            return b.avg_latency_ms - a.avg_latency_ms;
        });
        var maxItems = 15;
        var truncated = sorted.length > maxItems;
        sorted = sorted.slice(0, maxItems);

        var labels = sorted.map(function (idx) { return idx.index_uid; });
        var data = sorted.map(function (idx) { return idx.avg_latency_ms; });
        var bgColors = data.map(latencyColor);
        var borderColors = data.map(latencyBorder);

        // Dynamic height based on number of items
        canvas.parentElement.style.height = Math.max(200, sorted.length * 28 + 60) + 'px';

        return new Chart(canvas, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Avg Latency',
                    data: data,
                    backgroundColor: bgColors,
                    borderColor: borderColors,
                    borderWidth: 1,
                    borderRadius: 3,
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function (ctx) {
                                return ctx.parsed.x.toFixed(1) + 'ms';
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        beginAtZero: true,
                        title: { display: true, text: 'Avg Latency (ms)' },
                        grid: { color: colors.gridColor },
                    },
                    y: {
                        grid: { display: false },
                        ticks: {
                            font: { size: 10 },
                            callback: function (value, index) {
                                var label = this.getLabelForValue(value);
                                return label.length > 25 ? label.substring(0, 22) + '...' : label;
                            }
                        }
                    }
                }
            }
        });
    }

    /**
     * Chart 4: Fix Benchmark Before/After
     * Grouped vertical bar chart showing before and after latencies.
     */
    function createFixComparisonChart(canvasId, beforeMs, afterMs, improved) {
        var canvas = document.getElementById(canvasId);
        if (!canvas) return null;

        return new Chart(canvas, {
            type: 'bar',
            data: {
                labels: ['Before', 'After'],
                datasets: [{
                    label: 'Avg Latency',
                    data: [beforeMs, afterMs],
                    backgroundColor: [
                        colors.grayBg,
                        improved ? colors.greenBg : colors.redBg,
                    ],
                    borderColor: [
                        colors.gray,
                        improved ? colors.green : colors.red,
                    ],
                    borderWidth: 1,
                    borderRadius: 3,
                    barPercentage: 0.6,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function (ctx) {
                                return ctx.parsed.y.toFixed(2) + 'ms';
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        title: { display: true, text: 'Latency (ms)' },
                        grid: { color: colors.gridColor },
                    },
                    x: {
                        grid: { display: false },
                    }
                }
            }
        });
    }

    return {
        colors: colors,
        createQueryTypeChart: createQueryTypeChart,
        createPercentileChart: createPercentileChart,
        createIndexComparisonChart: createIndexComparisonChart,
        createFixComparisonChart: createFixComparisonChart,
    };
})();
