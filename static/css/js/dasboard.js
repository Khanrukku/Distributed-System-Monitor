// Dashboard JavaScript
class SystemMonitorDashboard {
    constructor() {
        this.socket = null;
        this.chart = null;
        this.metricsData = [];
        this.maxDataPoints = 50;
        this.connectionStatus = document.getElementById('connection-status');
        this.connectionText = document.getElementById('connection-text');
        
        this.init();
    }
    
    init() {
        this.initializeSocket();
        this.initializeChart();
        this.loadInitialData();
        this.setupEventListeners();
    }
    
    initializeSocket() {
        // Initialize Socket.IO connection
        this.socket = io();
        
        // Connection events
        this.socket.on('connect', () => {
            console.log('Connected to server');
            this.updateConnectionStatus(true);
        });
        
        this.socket.on('disconnect', () => {
            console.log('Disconnected from server');
            this.updateConnectionStatus(false);
        });
        
        // Data events
        this.socket.on('metrics_update', (data) => {
            this.handleMetricsUpdate(data);
        });
        
        this.socket.on('alert_update', (data) => {
            this.handleAlertUpdate(data);
        });
        
        this.socket.on('status', (data) => {
            console.log('Status:', data.msg);
        });
    }
    
    updateConnectionStatus(isConnected) {
        if (isConnected) {
            this.connectionStatus.className = 'status-dot online';
            this.connectionText.textContent = 'Connected';
        } else {
            this.connectionStatus.className = 'status-dot offline';
            this.connectionText.textContent = 'Disconnected';
        }
    }
    
    initializeChart() {
        const ctx = document.getElementById('systemChart').getContext('2d');
        
        this.chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'CPU Usage (%)',
                        data: [],
                        borderColor: '#4299e1',
                        backgroundColor: 'rgba(66, 153, 225, 0.1)',
                        tension: 0.4,
                        fill: true
                    },
                    {
                        label: 'Memory Usage (%)',
                        data: [],
                        borderColor: '#48bb78',
                        backgroundColor: 'rgba(72, 187, 120, 0.1)',
                        tension: 0.4,
                        fill: true
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    legend: {
                        position: 'top',
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return context.dataset.label + ': ' + context.parsed.y.toFixed(1) + '%';
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        display: true,
                        title: {
                            display: true,
                            text: 'Time'
                        },
                        grid: {
                            display: false
                        }
                    },
                    y: {
                        display: true,
                        title: {
                            display: true,
                            text: 'Usage (%)'
                        },
                        min: 0,
                        max: 100,
                        grid: {
                            color: 'rgba(0, 0, 0, 0.1)'
                        }
                    }
                },
                animation: {
                    duration: 750
                }
            }
        });
    }
    
    async loadInitialData() {
        try {
            // Load latest metrics
            const latestResponse = await fetch('/api/metrics/latest');
            if (latestResponse.ok) {
                const latestData = await latestResponse.json();
                this.updateMetricsDisplay(latestData);
            }
            
            // Load historical data for chart
            const historyResponse = await fetch('/api/metrics/history');
            if (historyResponse.ok) {
                const historyData = await historyResponse.json();
                this.initializeChartData(historyData);
            }
            
            // Load alerts
            const alertsResponse = await fetch('/api/alerts');
            if (alertsResponse.ok) {
                const alertsData = await alertsResponse.json();
                this.displayAlerts(alertsData);
            }
            
        } catch (error) {
            console.error('Error loading initial data:', error);
        }
    }
    
    initializeChartData(historyData) {
        if (!historyData || historyData.length === 0) return;
        
        // Take last 30 data points for better visualization
        const recentData = historyData.slice(-30);
        
        const labels = recentData.map(data => {
            const date = new Date(data.timestamp);
            return date.toLocaleTimeString('en-US', { 
                hour12: false, 
                hour: '2-digit', 
                minute: '2-digit' 
            });
        });
        
        const cpuData = recentData.map(data => data.cpu.percent);
        const memoryData = recentData.map(data => data.memory.percent);
        
        this.chart.data.labels = labels;
        this.chart.data.datasets[0].data = cpuData;
        this.chart.data.datasets[1].data = memoryData;
        this.chart.update();
        
        this.metricsData = recentData;
    }
    
    handleMetricsUpdate(data) {
        this.updateMetricsDisplay(data);
        this.updateChart(data);
        this.updateSystemInfo(data);
    }
    
    updateMetricsDisplay(data) {
        // Update metric cards with animation
        this.updateMetricValue('cpu-value', data.cpu.percent, '%');
        this.updateMetricValue('memory-value', data.memory.percent, '%');
        this.updateMetricValue('disk-value', data.disk.percent, '%');
        this.updateMetricValue('processes-value', data.processes, '');
        
        // Update last update time
        const updateTime = new Date(data.timestamp);
        document.getElementById('last-update').textContent = 
            updateTime.toLocaleTimeString();
    }
    
    updateMetricValue(elementId, value, unit) {
        const element = document.getElementById(elementId);
        const formattedValue = typeof value === 'number' ? 
            (unit === '%' ? value.toFixed(1) : value.toString()) : '--';
        
        // Add animation class
        element.classList.add('pulse');
        element.textContent = formattedValue;
        
        // Update color based on value (for percentage metrics)
        if (unit === '%') {
            element.className = 'metric-value';
            if (value > 80) {
                element.classList.add('critical');
            } else if (value > 60) {
                element.classList.add('warning');
            }
        }
        
        // Remove animation class after animation completes
        setTimeout(() => {
            element.classList.remove('pulse');
        }, 1000);
    }
    
    updateChart(data) {
        // Add new data point
        this.metricsData.push(data);
        
        // Keep only last maxDataPoints
        if (this.metricsData.length > this.maxDataPoints) {
            this.metricsData.shift();
        }
        
        // Update chart data
        const timeLabel = new Date(data.timestamp).toLocaleTimeString('en-US', { 
            hour12: false, 
            hour: '2-digit', 
            minute: '2-digit',
            second: '2-digit'
        });
        
        this.chart.data.labels.push(timeLabel);
        this.chart.data.datasets[0].data.push(data.cpu.percent);
        this.chart.data.datasets[1].data.push(data.memory.percent);
        
        // Remove old data points
        if (this.chart.data.labels.length > this.maxDataPoints) {
            this.chart.data.labels.shift();
            this.chart.data.datasets[0].data.shift();
            this.chart.data.datasets[1].data.shift();
        }
        
        this.chart.update('none'); // No animation for real-time updates
    }
    
    updateSystemInfo(data) {
        document.getElementById('cpu-cores').textContent = data.cpu.count;
        document.getElementById('total-memory').textContent = 
            this.formatBytes(data.memory.total);
        document.getElementById('total-disk').textContent = 
            this.formatBytes(data.disk.total);
    }
    
    handleAlertUpdate(data) {
        this.addAlertToDisplay(data);
        this.showNotification(data);
    }
    
    addAlertToDisplay(alert) {
        const alertsContainer = document.getElementById('alerts-container');
        
        // Remove "No alerts" message if present
        if (alertsContainer.textContent.includes('No alerts')) {
            alertsContainer.innerHTML = '';
        }
        
        const alertElement = this.createAlertElement(alert);
        alertsContainer.insertBefore(alertElement, alertsContainer.firstChild);
        
        // Keep only last 10 alerts
        while (alertsContainer.children.length > 10) {
            alertsContainer.removeChild(alertsContainer.lastChild);
        }
    }
    
    createAlertElement(alert) {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert-item ${alert.severity}`;
        
        const alertTime = new Date(alert.timestamp).toLocaleTimeString();
        
        alertDiv.innerHTML = `
            <div class="alert-header">
                <span class="alert-type ${alert.severity}">${alert.type}</span>
                <span class="alert-time">${alertTime}</span>
            </div>
            <div class="alert-message">${alert.message}</div>
        `;
        
        return alertDiv;
    }
    
    displayAlerts(alerts) {
        const alertsContainer = document.getElementById('alerts-container');
        
        if (!alerts || alerts.length === 0) {
            alertsContainer.innerHTML = '<p>No alerts to display</p>';
            return;
        }
        
        alertsContainer.innerHTML = '';
        alerts.slice(0, 10).forEach(alert => {
            const alertElement = this.createAlertElement(alert);
            alertsContainer.appendChild(alertElement);
        });
    }
    
    showNotification(alert) {
        // Create a browser notification if supported
        if ('Notification' in window && Notification.permission === 'granted') {
            new Notification(`System Alert: ${alert.type.toUpperCase()}`, {
                body: alert.message,
                icon: '/static/favicon.ico',
                tag: `alert-${alert.type}`,
                requireInteraction: alert.severity === 'critical'
            });
        }
    }
    
    setupEventListeners() {
        // Request notification permission
        if ('Notification' in window && Notification.permission === 'default') {
            Notification.requestPermission();
        }
        
        // Refresh data button (if you add one)
        const refreshButton = document.getElementById('refresh-btn');
        if (refreshButton) {
            refreshButton.addEventListener('click', () => {
                this.loadInitialData();
            });
        }
        
        // Handle page visibility changes
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) {
                // Reload data when page becomes visible again
                this.loadInitialData();
            }
        });
        
        // Handle window resize for chart
        window.addEventListener('resize', () => {
            if (this.chart) {
                this.chart.resize();
            }
        });
    }
    
    formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    // Health check method
    async checkHealth() {
        try {
            const response = await fetch('/api/health');
            const health = await response.json();
            console.log('System Health:', health);
            return health;
        } catch (error) {
            console.error('Health check failed:', error);
            return null;
        }
    }
}

// Initialize dashboard when page loads
document.addEventListener('DOMContentLoaded', () => {
    const dashboard = new SystemMonitorDashboard();
    
    // Make dashboard globally accessible for debugging
    window.dashboard = dashboard;
    
    console.log('System Monitor Dashboard initialized');
});

// Error handling
window.addEventListener('error', (event) => {
    console.error('Dashboard error:', event.error);
});

// Unhandled promise rejection handler
window.addEventListener('unhandledrejection', (event) => {
    console.error('Unhandled promise rejection:', event.reason);
});
