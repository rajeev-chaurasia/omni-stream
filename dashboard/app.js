/**
 * OmniStream Dashboard
 * Real-time telemetry visualization for autonomous vehicle simulation.
 */

const WS_URL = 'ws://localhost:8765';
const VISUAL_UPDATE_MS = 66;  // ~15 FPS for smooth rendering

let ws = null;
let packetsReceived = 0;
let startTime = null;
let lastPacketTime = null;
let lastVisualUpdate = 0;
let tickTimes = [];

let lidarChart = null;
let imuChart = null;

const imuHistory = { labels: [], x: [], y: [], z: [] };

function init() {
    initCharts();
    connectWebSocket();
    startUptime();
}

function initCharts() {
    lidarChart = new Chart(document.getElementById('lidarChart'), {
        type: 'polarArea',
        data: { labels: [], datasets: [{ data: [], backgroundColor: [], borderWidth: 1 }] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 0 },
            plugins: { legend: { display: false } },
            scales: { r: { beginAtZero: true, max: 15, ticks: { display: false } } }
        }
    });

    imuChart = new Chart(document.getElementById('imuChart'), {
        type: 'line',
        data: {
            labels: imuHistory.labels,
            datasets: [
                { label: 'X', data: imuHistory.x, borderColor: '#ff6b6b', fill: false, tension: 0.3, pointRadius: 0 },
                { label: 'Y', data: imuHistory.y, borderColor: '#4ecdc4', fill: false, tension: 0.3, pointRadius: 0 },
                { label: 'Z', data: imuHistory.z, borderColor: '#ffe66d', fill: false, tension: 0.3, pointRadius: 0 }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 0 },
            scales: { x: { display: false } }
        }
    });
}

function connectWebSocket() {
    setStatus('connecting');
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
        setStatus('connected');
        startTime = Date.now();
    };

    ws.onclose = () => {
        setStatus('disconnected');
        setTimeout(connectWebSocket, 2000);
    };

    ws.onerror = () => setStatus('error');

    ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === 'telemetry') handleTelemetry(msg.data);
    };
}

function handleTelemetry(data) {
    const now = Date.now();

    if (lastPacketTime) {
        tickTimes.push(now - lastPacketTime);
        if (tickTimes.length > 60) tickTimes.shift();
    }
    lastPacketTime = now;
    packetsReceived++;

    if (now - lastVisualUpdate < VISUAL_UPDATE_MS) return;
    lastVisualUpdate = now;

    document.getElementById('vehicleId').textContent = data.vehicle_id;
    updateLidar(data.lidar_scan);
    updateIMU(data.imu_reading);
    updateBattery(data.battery_level);
    updateMetrics(data.timestamp);
}

function updateLidar(scan) {
    if (!scan?.length) return;

    const step = 8;
    const data = [], labels = [], colors = [];

    for (let i = 0; i < scan.length; i += step) {
        data.push(scan[i]);
        labels.push(`${Math.round(i / scan.length * 360)}°`);
        colors.push(`hsla(${180 + (i / scan.length) * 60}, 80%, 50%, 0.7)`);
    }

    lidarChart.data.labels = labels;
    lidarChart.data.datasets[0].data = data;
    lidarChart.data.datasets[0].backgroundColor = colors;
    lidarChart.update('none');

    document.getElementById('lidarPoints').textContent = `${scan.length} pts`;
}

function updateIMU(imu) {
    if (!imu) return;

    document.getElementById('imuX').textContent = imu.accel_x.toFixed(3);
    document.getElementById('imuY').textContent = imu.accel_y.toFixed(3);
    document.getElementById('imuZ').textContent = imu.accel_z.toFixed(3);

    imuHistory.labels.push('');
    imuHistory.x.push(imu.accel_x);
    imuHistory.y.push(imu.accel_y);
    imuHistory.z.push(imu.accel_z);

    if (imuHistory.labels.length > 100) {
        imuHistory.labels.shift();
        imuHistory.x.shift();
        imuHistory.y.shift();
        imuHistory.z.shift();
    }

    imuChart.update('none');
}

function updateBattery(level) {
    const pct = Math.max(0, Math.min(100, level));
    const el = document.getElementById('batteryLevel');

    el.style.height = `${pct}%`;
    el.style.background = pct > 50 ? 'linear-gradient(to top, #00ff88, #00d4ff)' :
        pct > 20 ? 'linear-gradient(to top, #ff8800, #ffe66d)' :
            'linear-gradient(to top, #ff4444, #ff8800)';

    document.getElementById('batteryText').textContent = `${pct.toFixed(1)}%`;
    document.getElementById('voltage').textContent = `${(44 + pct / 100 * 8).toFixed(1)}V`;
    document.getElementById('current').textContent = `${(12 + pct / 100 * 2).toFixed(1)}A`;
    document.getElementById('range').textContent = `${Math.round(pct * 1.5)} km`;
}

function updateMetrics(timestamp) {
    if (tickTimes.length) {
        const avg = tickTimes.reduce((a, b) => a + b) / tickTimes.length;
        document.getElementById('tickRate').textContent = Math.round(1000 / avg);
    }

    const latency = Math.max(0, (Date.now() * 1000 - timestamp) / 1000);
    document.getElementById('latency').textContent = latency.toFixed(1);
    document.getElementById('packetsTotal').textContent = formatNum(packetsReceived);
}

function setStatus(status) {
    const el = document.getElementById('connectionStatus');
    const txt = document.getElementById('connectionText');
    el.className = 'status-indicator' + (status === 'connected' ? ' connected' : '');
    txt.textContent = status.charAt(0).toUpperCase() + status.slice(1);
}

function startUptime() {
    setInterval(() => {
        if (!startTime) return;
        const s = Math.floor((Date.now() - startTime) / 1000);
        document.getElementById('uptime').textContent =
            `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
    }, 1000);
}

function formatNum(n) {
    return n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? (n / 1e3).toFixed(1) + 'K' : n;
}

document.addEventListener('DOMContentLoaded', init);
