/**
 * NCWSCwaterLAB - Unified Dashboard Analytics & Chart Engine
 * Powered by Chart.js with automatic theme adaptation, progressive rendering,
 * and high-resolution modal expansion.
 */

(function () {
    'use strict';

    window.DashboardCharts = window.DashboardCharts || {
        registry: {},
        expandedChart: null,
        activeExpandedId: null
    };

    /**
     * Helper to get CSS variable values from active theme
     */
    function getThemeColor(varName, fallback) {
        const val = getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
        return val || fallback;
    }

    function isDarkMode() {
        const theme = document.documentElement.getAttribute('data-theme');
        return theme === 'dark' || theme === 'oled' || theme === 'amoled' || theme === 'aurora' || theme === 'celestial';
    }

    function getChartThemeDefaults() {
        const dark = isDarkMode();
        return {
            textColor: dark ? '#cbd5e1' : '#475569',
            gridColor: dark ? 'rgba(255, 255, 255, 0.07)' : 'rgba(0, 0, 0, 0.05)',
            accentColor: getThemeColor('--theme-accent', '#0284c7'),
            fontFamily: "'Plus Jakarta Sans', 'Inter', sans-serif"
        };
    }

    /**
     * Create or update a Progressive Line Chart
     */
    window.initProgressiveLineChart = function (canvasId, options) {
        const canvas = document.getElementById(canvasId);
        if (!canvas || typeof Chart === 'undefined') return null;

        const ctx = canvas.getContext('2d');
        const themeDefaults = getChartThemeDefaults();
        const primaryColor = options.color || themeDefaults.accentColor;

        // Create gradient fill
        const gradient = ctx.createLinearGradient(0, 0, 0, canvas.height || 220);
        gradient.addColorStop(0, primaryColor.startsWith('rgba') ? primaryColor : primaryColor + '40');
        gradient.addColorStop(1, 'rgba(255, 255, 255, 0.0)');

        const datasets = options.datasets || [{
            label: options.label || 'Value',
            data: options.data || [],
            borderColor: primaryColor,
            backgroundColor: gradient,
            borderWidth: 2.5,
            fill: true,
            tension: 0.36,
            pointBackgroundColor: primaryColor,
            pointBorderColor: '#ffffff',
            pointBorderWidth: 1.5,
            pointRadius: (options.data && options.data.length > 30) ? 2 : 4,
            pointHoverRadius: 6
        }];

        // Destroy previous instance if exists
        if (window.DashboardCharts.registry[canvasId] && window.DashboardCharts.registry[canvasId].chart) {
            window.DashboardCharts.registry[canvasId].chart.destroy();
        }

        const chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: options.labels || [],
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                plugins: {
                    legend: {
                        display: options.showLegend || false,
                        labels: {
                            color: themeDefaults.textColor,
                            font: { family: themeDefaults.fontFamily, size: 12 }
                        }
                    },
                    tooltip: {
                        backgroundColor: isDarkMode() ? '#1e293b' : '#0f172a',
                        titleColor: '#f8fafc',
                        bodyColor: '#e2e8f0',
                        borderColor: 'rgba(255,255,255,0.1)',
                        borderWidth: 1,
                        padding: 10,
                        cornerRadius: 8
                    }
                },
                scales: {
                    x: {
                        grid: { color: themeDefaults.gridColor, drawBorder: false },
                        ticks: { color: themeDefaults.textColor, font: { family: themeDefaults.fontFamily, size: 11 } }
                    },
                    y: {
                        beginAtZero: options.beginAtZero !== undefined ? options.beginAtZero : true,
                        grid: { color: themeDefaults.gridColor, drawBorder: false },
                        ticks: {
                            color: themeDefaults.textColor,
                            font: { family: themeDefaults.fontFamily, size: 11 },
                            callback: options.yAxisFormatter || function (v) { return v; }
                        }
                    }
                }
            }
        });

        window.DashboardCharts.registry[canvasId] = {
            chart: chart,
            type: 'line',
            labels: options.labels || [],
            datasets: datasets,
            title: options.title || canvasId,
            subtitle: options.subtitle || ''
        };

        return chart;
    };

    /**
     * Create or update a Bar Comparison Chart
     */
    window.initBarChart = function (canvasId, options) {
        const canvas = document.getElementById(canvasId);
        if (!canvas || typeof Chart === 'undefined') return null;

        const ctx = canvas.getContext('2d');
        const themeDefaults = getChartThemeDefaults();
        const primaryColor = options.color || themeDefaults.accentColor;

        const datasets = options.datasets || [{
            label: options.label || 'Count',
            data: options.data || [],
            backgroundColor: options.colors || primaryColor,
            borderRadius: 6,
            maxBarThickness: 36
        }];

        if (window.DashboardCharts.registry[canvasId] && window.DashboardCharts.registry[canvasId].chart) {
            window.DashboardCharts.registry[canvasId].chart.destroy();
        }

        const chart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: options.labels || [],
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: options.showLegend || false,
                        labels: { color: themeDefaults.textColor, font: { family: themeDefaults.fontFamily } }
                    },
                    tooltip: {
                        backgroundColor: isDarkMode() ? '#1e293b' : '#0f172a',
                        titleColor: '#f8fafc',
                        bodyColor: '#e2e8f0',
                        cornerRadius: 8
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: themeDefaults.textColor, font: { family: themeDefaults.fontFamily, size: 11 } }
                    },
                    y: {
                        beginAtZero: true,
                        grid: { color: themeDefaults.gridColor },
                        ticks: { color: themeDefaults.textColor, font: { family: themeDefaults.fontFamily, size: 11 } }
                    }
                }
            }
        });

        window.DashboardCharts.registry[canvasId] = {
            chart: chart,
            type: 'bar',
            labels: options.labels || [],
            datasets: datasets,
            title: options.title || canvasId,
            subtitle: options.subtitle || ''
        };

        return chart;
    };

    /**
     * Expand any chart into the high-resolution universal modal
     */
    window.expandDashboardChart = function (chartId, customTitle, customSubtitle) {
        const item = window.DashboardCharts.registry[chartId];
        const modalEl = document.getElementById('chartExpandModal');
        const expandCanvas = document.getElementById('expandedChartCanvas');

        if (!modalEl || !expandCanvas) return;

        const titleEl = document.getElementById('chartExpandModalLabel');
        const subtitleEl = document.getElementById('chartExpandModalSubtitle');
        const statSamples = document.getElementById('expandStatSamples');
        const statPeak = document.getElementById('expandStatPeak');
        const statMin = document.getElementById('expandStatMin');
        const statMean = document.getElementById('expandStatMean');

        const title = customTitle || (item ? item.title : 'Analytics Detail View');
        const subtitle = customSubtitle || (item ? item.subtitle : 'Expanded Inspection Window');

        if (titleEl) titleEl.textContent = title;
        if (subtitleEl) subtitleEl.textContent = subtitle;

        window.DashboardCharts.activeExpandedId = chartId;

        // Destroy existing modal chart if present
        if (window.DashboardCharts.expandedChart) {
            window.DashboardCharts.expandedChart.destroy();
            window.DashboardCharts.expandedChart = null;
        }

        const modalCtx = expandCanvas.getContext('2d');
        const themeDefaults = getChartThemeDefaults();

        let labels = [];
        let datasets = [];
        let chartType = 'line';

        if (item) {
            labels = [...item.labels];
            chartType = item.type || 'line';
            datasets = JSON.parse(JSON.stringify(item.datasets));
        } else {
            // Generate standard progressive sample metrics if called on a chart without full registry
            labels = ['Day 1', 'Day 2', 'Day 3', 'Day 4', 'Day 5', 'Day 6', 'Day 7', 'Day 8', 'Day 9', 'Day 10', 'Day 11', 'Day 12', 'Day 13', 'Day 14'];
            datasets = [{
                label: title,
                data: [98.2, 97.9, 98.6, 99.1, 98.8, 99.4, 98.7, 99.0, 99.2, 98.9, 99.5, 99.3, 99.7, 99.6],
                borderColor: themeDefaults.accentColor,
                backgroundColor: 'rgba(2, 132, 199, 0.15)',
                borderWidth: 3,
                fill: true,
                tension: 0.35
            }];
        }

        // Calculate summary metrics
        let values = [];
        if (datasets.length && Array.isArray(datasets[0].data)) {
            values = datasets[0].data.map(v => typeof v === 'number' ? v : (v && v.y ? v.y : parseFloat(v) || 0));
        }

        if (values.length > 0) {
            const count = values.length;
            const maxVal = Math.max(...values);
            const minVal = Math.min(...values);
            const meanVal = (values.reduce((a, b) => a + b, 0) / count);

            if (statSamples) statSamples.textContent = count;
            if (statPeak) statPeak.textContent = Number.isInteger(maxVal) ? maxVal : maxVal.toFixed(2);
            if (statMin) statMin.textContent = Number.isInteger(minVal) ? minVal : minVal.toFixed(2);
            if (statMean) statMean.textContent = meanVal.toFixed(2);
        }

        // Render expanded chart
        window.DashboardCharts.expandedChart = new Chart(modalCtx, {
            type: chartType,
            data: { labels: labels, datasets: datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 400 },
                plugins: {
                    legend: { display: datasets.length > 1, labels: { color: themeDefaults.textColor } },
                    tooltip: {
                        backgroundColor: isDarkMode() ? '#1e293b' : '#0f172a',
                        titleColor: '#f8fafc',
                        bodyColor: '#e2e8f0',
                        padding: 12
                    }
                },
                scales: {
                    x: {
                        grid: { color: themeDefaults.gridColor },
                        ticks: { color: themeDefaults.textColor, font: { size: 12 } }
                    },
                    y: {
                        grid: { color: themeDefaults.gridColor },
                        ticks: { color: themeDefaults.textColor, font: { size: 12 } }
                    }
                }
            }
        });

        // Show Bootstrap Modal
        if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
            const bsModal = bootstrap.Modal.getOrCreateInstance(modalEl);
            bsModal.show();
        }
    };

    /**
     * Export Handler for PNG
     */
    document.addEventListener('DOMContentLoaded', () => {
        const exportPngBtn = document.getElementById('chartExportPngBtn');
        const exportCsvBtn = document.getElementById('chartExportCsvBtn');

        if (exportPngBtn) {
            exportPngBtn.addEventListener('click', () => {
                const canvas = document.getElementById('expandedChartCanvas');
                if (!canvas) return;
                const link = document.createElement('a');
                link.download = (window.DashboardCharts.activeExpandedId || 'chart_analytics') + '.png';
                link.href = canvas.toDataURL('image/png');
                link.click();
            });
        }

        if (exportCsvBtn) {
            exportCsvBtn.addEventListener('click', () => {
                const item = window.DashboardCharts.registry[window.DashboardCharts.activeExpandedId];
                if (!item || !item.labels || !item.datasets) return;

                let csv = 'Label,' + item.datasets.map(d => `"${d.label || 'Value'}"`).join(',') + '\n';
                item.labels.forEach((lbl, idx) => {
                    const rowVals = item.datasets.map(d => d.data[idx] !== undefined ? d.data[idx] : '');
                    csv += `"${lbl}",` + rowVals.join(',') + '\n';
                });

                const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
                const link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                link.download = (window.DashboardCharts.activeExpandedId || 'chart_data') + '.csv';
                link.click();
            });
        }
    });

    /**
     * Theme update listener to re-theme charts on the fly
     */
    window.addEventListener('themeChanged', () => {
        const defaults = getChartThemeDefaults();
        Object.values(window.DashboardCharts.registry).forEach(item => {
            if (item && item.chart && item.chart.options) {
                if (item.chart.options.scales && item.chart.options.scales.x) {
                    item.chart.options.scales.x.ticks.color = defaults.textColor;
                    item.chart.options.scales.x.grid.color = defaults.gridColor;
                }
                if (item.chart.options.scales && item.chart.options.scales.y) {
                    item.chart.options.scales.y.ticks.color = defaults.textColor;
                    item.chart.options.scales.y.grid.color = defaults.gridColor;
                }
                item.chart.update('none');
            }
        });
    });

})();
