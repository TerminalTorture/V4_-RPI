// Use global variables from config.js instead of imports

let timeLabels = [];
let charts = {}; // Use window.charts if sharing state with sensor.js is intended
let registerDefinitions = null; // Store fetched definitions
let currentRange = '30m'; // Default range from new select element
let customStartDate = null;
let customEndDate = null;

document.addEventListener("DOMContentLoaded", async () => {
    console.log("Historical page DOM loaded. Fetching definitions...");
    // Load settings from localStorage
    try {
        document.getElementById("unitName").textContent = localStorage.getItem("unitName") || "Unit: XX";
        document.getElementById("profileInfo").textContent = localStorage.getItem("profileInfo") || "10kW / 250kWh";
        document.getElementById("siteName").textContent = "Site: " + (localStorage.getItem("siteName") || "Singapore");
    } catch (e) {
        console.error("Error loading settings from localStorage:", e);
    }

    // --- Fetch Register Definitions ---
    try {
        const response = await fetch('/api/registers/definitions');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        registerDefinitions = await response.json();
        console.log("✅ Register definitions fetched successfully:", registerDefinitions);

        // --- Initialize UI based on definitions ---
        initializeHistoricalUI(registerDefinitions);
        // Removed populateVariableSelection call, now handled by export.js

        // --- Fetch Initial Data ---
        // Get the default range from the select element
        const rangeSelect = document.getElementById('rangeSelect');
        currentRange = rangeSelect ? rangeSelect.value : '30m'; // Fallback if element not ready
        fetchHistoricalData(currentRange); // Fetch data for the default range

    } catch (error) {
        console.error("❌ Failed to fetch or process register definitions:", error);
        displayHistoricalError(error);
    }

    // --- Setup Event Listeners ---
    setupEventListeners();
});

// --- Initialize Historical UI (Charts) ---
function initializeHistoricalUI(definitions) {
    // Filter definitions.registers
    const historicalViewRegisters = definitions.registers?.filter((reg, index) => {
        const ui = reg.ui;
        const view = ui?.view;
        const component = ui?.component;
        const isHistoricalView = (view === 'historical' || (Array.isArray(view) && view.includes('historical')));
        const isLineChart = (component === 'line_chart' || (Array.isArray(component) && component.includes('line_chart')));
        const shouldInclude = isHistoricalView && isLineChart;
        return shouldInclude;
    }) || [];

    // How many registers were filtered?
    console.log(`initializeHistoricalUI: Found ${historicalViewRegisters.length} registers for historical line charts.`);

    const chartsContainer = document.getElementById('historical-charts-container');
    if (!chartsContainer) {
        console.error("❌ Historical charts container #historical-charts-container not found!");
        return;
    }
    chartsContainer.innerHTML = ''; // Clear placeholders

    const groupsForCharts = {};
    historicalViewRegisters.forEach(reg => {
        const group = reg.group || 'default';
        const uiConfig = reg.ui || {};
        if (!groupsForCharts[group]) {
            groupsForCharts[group] = {
                variables: [],
                title: (uiConfig.chartTitle || group.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())) + (reg.unit ? ` (${reg.unit})` : '')
            };
        }
        groupsForCharts[group].variables.push(reg);
    });

    // How many chart groups were created?
    console.log(`initializeHistoricalUI: Created ${Object.keys(groupsForCharts).length} chart groups.`);

    // Create Chart Canvases
    Object.entries(groupsForCharts).forEach(([groupKey, groupInfo]) => {
        const chartId = `chart-${groupKey}`;
        const card = document.createElement('div');
        card.className = 'md3-card overflow-hidden';
        card.innerHTML = `
            <div class="bg-primary-container p-4">
                 <h3 class="text-on-primary-container font-medium">${groupInfo.title}</h3>
             </div>
             <div class="p-4" style="height: 300px; position: relative;">
                 <canvas id="${chartId}"></canvas>
             </div>
             <button onclick="resetZoom('${chartId}')" class="md3-button-text m-2">Reset Zoom</button>
        `;
        chartsContainer.appendChild(card);
        // Initialize chart structure (data added later)
        createOrUpdateChart(chartId, [], []); // Initialize empty
    });
}

// --- Display Error Message ---
function displayHistoricalError(error) {
    const chartsContainer = document.getElementById('historical-charts-container');
    if (chartsContainer) {
        // Use a simpler error display within the container
        chartsContainer.innerHTML = `
            <div class="md3-card p-6 text-center text-error col-span-full">
                <h2 class="text-xl font-semibold mb-4">Failed to Load Historical Charts</h2>
                <p>Could not load necessary configuration or data.</p>
                <p class="text-sm mt-2">Error: ${error.message}</p>
            </div>
        `;
    }
}

// Downsample data (remains the same)
function downsampleData(data, maxPoints = 500) { // Increased maxPoints for historical
    if (!Array.isArray(data) || data.length <= maxPoints) {
        return data;
    }
    const step = Math.ceil(data.length / maxPoints);
    const downsampled = data.filter((_, index) => index % step === 0);
    console.log(`📊 Downsampling complete. Original: ${data.length}, Reduced: ${downsampled.length}`);
    return downsampled;
}

// --- Fetch Historical Data ---
function fetchHistoricalData(range, start = null, end = null) {
    currentRange = range; // Update global state
    customStartDate = start instanceof Date ? start : null; // Ensure Date object or null
    customEndDate = end instanceof Date ? end : null;     // Ensure Date object or null

    let url = `/api/historical-data?range=${range}`;
    if (range === "custom" && customStartDate && customEndDate) {
        // Format dates as YYYY-MM-DDTHH:MM for the API
        // The backend will interpret these as GMT+8
        // These are local dates from the date picker, representing the user's desired range in their local view.
        const startStr = `${customStartDate.getFullYear()}-${String(customStartDate.getMonth() + 1).padStart(2, '0')}-${String(customStartDate.getDate()).padStart(2, '0')}T${String(customStartDate.getHours()).padStart(2, '0')}:${String(customStartDate.getMinutes()).padStart(2, '0')}`;
        const endStr = `${customEndDate.getFullYear()}-${String(customEndDate.getMonth() + 1).padStart(2, '0')}-${String(customEndDate.getDate()).padStart(2, '0')}T${String(customEndDate.getHours()).padStart(2, '0')}:${String(customEndDate.getMinutes()).padStart(2, '0')}`;
        url += `&start=${encodeURIComponent(startStr)}&end=${encodeURIComponent(endStr)}`;
        console.log(`Fetching custom range: ${startStr} to ${endStr} (sent as local, interpreted as GMT+8 by backend)`);
    } else if (range === "custom") {
        console.error("❌ Custom range selected but start or end date is missing or invalid.");
        alert("Please select valid start and end dates for the custom range.");
        showLoadingIndicator(false); // Hide indicator if shown
        return; // Don't proceed with fetch
    }

    console.log(`📊 Fetching historical data from: ${url}`);
    showLoadingIndicator(true); // Show spinner

    fetch(url)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log(`✅ Received ${data.length} historical records.`);
            // Timestamps from backend are now ISO8601 with GMT+8 offset (e.g., ...+08:00)
            // new Date() will parse these correctly into local time for display.
            const downsampled = downsampleData(data);
            updateCharts(downsampled); // Update charts with downsampled data
            showLoadingIndicator(false); // Hide spinner
        })
        .catch(error => {
            console.error('❌ Error fetching historical data:', error);
            showLoadingIndicator(false); // Hide spinner
            displayHistoricalError(error); // Show error in the chart area
        });
}

// --- Update Charts ---
function updateCharts(data) {
    if (!registerDefinitions) {
        console.error("Cannot update charts, register definitions not loaded.");
        return;
    }
    if (!Array.isArray(data)) {
        console.warn("No valid data received to update charts. Clearing charts.");
        // Clear charts if data is invalid or empty
         Object.values(charts).forEach(chart => {
             chart.data.labels = [];
             chart.data.datasets.forEach(ds => ds.data = []);
             chart.update();
         });
        return;
    }

    // Convert timestamps to Date objects. Backend sends ISO strings with offset.
    // new Date() correctly parses these into the browser's local time.
    timeLabels = data.map(entry => new Date(entry.timestamp));

    // Filter registerDefinitions.registers
    const historicalViewRegisters = registerDefinitions.registers?.filter((reg, index) => {
        const ui = reg.ui;
        const view = ui?.view;
        const component = ui?.component;
        const isHistoricalView = (view === 'historical' || (Array.isArray(view) && view.includes('historical')));
        const isLineChart = (component === 'line_chart' || (Array.isArray(component) && component.includes('line_chart')));
        const shouldInclude = isHistoricalView && isLineChart;
        return shouldInclude;
    }) || [];

    // How many registers were filtered?
    console.log(`updateCharts: Found ${historicalViewRegisters.length} registers for historical line charts.`);

    const groupsForCharts = {};
    historicalViewRegisters.forEach(reg => {
        const group = reg.group || 'default';
        if (!groupsForCharts[group]) {
            groupsForCharts[group] = { variables: [] };
        }
        groupsForCharts[group].variables.push(reg);
    });

    // How many groups to update?
    console.log(`updateCharts: Found ${Object.keys(groupsForCharts).length} chart groups to update.`);

    // Update each chart based on its group
    Object.entries(groupsForCharts).forEach(([groupKey, groupInfo]) => {
        const chartId = `chart-${groupKey}`;
        const datasets = groupInfo.variables.map(reg => ({
            label: reg.ui?.label || reg.name,
            data: data.map(entry => entry[reg.name] !== undefined ? entry[reg.name] : null),
            borderColor: reg.ui?.color || getRandomColor(),
            backgroundColor: (reg.ui?.color || getRandomColor()).replace('1)', '0.2)'),
            borderWidth: 1.5,
            tension: 0.1,
            pointRadius: data.length < 100 ? 2 : 0,
            pointHoverRadius: 5
        }));

        createOrUpdateChart(chartId, timeLabels, datasets);
    });
}

// --- Create or Update Chart ---
function createOrUpdateChart(chartId, labels, datasets) {
    const canvas = document.getElementById(chartId);
    if (!canvas) {
        console.error(`Canvas element with ID ${chartId} not found.`);
        return;
    }
    const ctx = canvas.getContext('2d');

    if (charts[chartId]) {
        // Update existing chart
        charts[chartId].data.labels = labels; // Assign Date objects
        charts[chartId].data.datasets = datasets;
        charts[chartId].resetZoom();
        charts[chartId].update('none');
        console.log(`🔄 Chart updated: ${chartId}`);
    } else {
        // Create new chart
        charts[chartId] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels, // Date objects (local time for display)
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        type: 'timeseries',
                        time: {
                            // parser: 'iso', // Not strictly needed, Chart.js auto-detects ISO
                            tooltipFormat: 'Pp HH:mm:ss OOOO', // Display local time with offset in tooltip
                            displayFormats: { 
                                millisecond: 'HH:mm:ss.SSS',
                                second: 'HH:mm:ss',
                                minute: 'HH:mm',
                                hour: 'HH:mm',
                                day: 'MMM d, HH:mm',
                                week: 'MMM d',
                                month: 'MMM yyyy',
                                quarter: 'qqq yyyy',
                                year: 'yyyy'
                            }
                        },
                        ticks: {
                            maxRotation: 0,
                            autoSkip: true,
                            maxTicksLimit: 15,
                            // Optional: callback to format ticks if needed, but default should be local time
                            // callback: function(value, index, ticks) {
                            //     return new Date(value).toLocaleTimeString(); // Example
                            // }
                        },
                        title: {
                           display: true,
                           text: 'Time (Browser Local Time)' // Clarify that x-axis is in browser's local time
                        }
                    },
                    y: {
                        beginAtZero: false
                    }
                },
                plugins: {
                    legend: { position: 'top', labels: { boxWidth: 12, padding: 10 } },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        callbacks: {
                            // Optional: Add unit to tooltip items
                            label: function(context) {
                                let label = context.dataset.label || '';
                                if (label) {
                                    label += ': ';
                                }
                                if (context.parsed.y !== null) {
                                    // Find the register definition to get the unit
                                    const regDef = registerDefinitions.registers.find(r => r.name === context.dataset.label || r.ui?.label === context.dataset.label);
                                    label += context.parsed.y + (regDef?.unit ? ` ${regDef.unit}` : '');
                                }
                                return label;
                            }
                        }
                     },
                    zoom: { // Zoom plugin configuration
                        pan: { enabled: true, mode: 'x', threshold: 5 }, // Enable panning
                        zoom: {
                            wheel: { enabled: true, speed: 0.1 }, // Enable wheel zoom
                            pinch: { enabled: true }, // Enable pinch zoom
                            mode: 'x', // Zoom only x-axis
                            drag: { enabled: false } // Disable drag-to-zoom (can conflict with pan)
                        }
                    }
                }
            }
        });
        console.log(`📊 Chart created: ${chartId}`);
    }
}

// --- Show/Hide Loading Indicator ---
function showLoadingIndicator(show) {
    const indicator = document.getElementById('loadingIndicator');
    if (indicator) {
        indicator.style.display = show ? 'flex' : 'none';
        // Prevent background interaction when loading
        document.body.style.pointerEvents = show ? 'none' : 'auto';
        indicator.style.pointerEvents = 'auto'; // Ensure spinner itself isn't blocked
    }
}

// --- Reset Zoom ---
window.resetZoom = function(chartId = null) {
    if (chartId && charts[chartId]) {
        charts[chartId].resetZoom();
        console.log(`Zoom reset for chart: ${chartId}`);
    } else if (!chartId) {
        // Reset zoom on all charts if no specific ID is given
        Object.values(charts).forEach(chart => chart.resetZoom());
        console.log("Zoom reset for all historical charts.");
    }
};

// --- Setup Event Listeners ---
function setupEventListeners() {
    // Range selection dropdown (handled by inline script in HTML)
    const rangeSelect = document.getElementById('rangeSelect');
    if (rangeSelect) {
        rangeSelect.addEventListener('change', function() {
            const range = this.value;
            const customDateDiv = document.getElementById('customDateRange');
            if (range === 'custom') {
                customDateDiv.classList.remove('hidden');
            } else {
                customDateDiv.classList.add('hidden');
                fetchHistoricalData(range); // Fetch data for standard ranges immediately
            }
        });
    } else {
        console.error("Range select element #rangeSelect not found.");
    }


    // Apply custom range button (handled by inline script in HTML)
    const fetchCustomBtn = document.getElementById('fetchCustomData');
     if (fetchCustomBtn) {
        fetchCustomBtn.addEventListener('click', () => {
            const startVal = document.getElementById('startDate').value;
            const endVal = document.getElementById('endDate').value;
            if (startVal && endVal) {
                const startDate = new Date(startVal);
                const endDate = new Date(endVal);
                if (!isNaN(startDate) && !isNaN(endDate) && startDate < endDate) {
                    fetchHistoricalData('custom', startDate, endDate);
                } else {
                    alert('Invalid date range. Ensure start date is before end date.');
                }
            } else {
                alert('Please select both start and end dates.');
            }
        });
     } else {
        console.error("Fetch custom data button #fetchCustomData not found.");
    }


    // Download button for 30 days (specific action handled by export.js)
    // We might still need a listener here if export.js doesn't handle the *click* itself
    const download30DaysBtn = document.getElementById('download30Days');
    if (download30DaysBtn) {
        // Listener moved to export.js as it handles the fetchAndDownloadCSV logic
        console.log("Download 30 days button found, handled by export.js");
    }

    // General Download button (handled by export.js)
    const downloadCsvButton = document.getElementById('downloadCsvButton');
    if (downloadCsvButton) {
        // Listener moved to export.js
        console.log("General Download CSV button found, handled by export.js");
    }

    // Hamburger menu (handled by inline script in HTML)
    const hamburgerMenu = document.getElementById('hamburger-menu');
    if (hamburgerMenu) {
        console.log("Hamburger menu found, handled by inline script.");
    }

    const sidebarOverlay = document.getElementById('sidebar-overlay');
    if (sidebarOverlay) {
         console.log("Sidebar overlay found, handled by inline script.");
    }

    // Custom date inputs visibility toggle for download range (handled by inline script in HTML)
     const downloadRangeSelect = document.getElementById('downloadRange');
     if (downloadRangeSelect) {
         console.log("Download range select found, handled by inline script.");
     }
}

// --- Remove unused functions previously related to export ---
// function populateVariableSelection(definitions) { ... } -> Removed
// function toggleDropdown() { ... } -> Removed
// function filterVariables() { ... } -> Removed
// window.onclick handler for dropdown -> Removed

// --- Helper function for random colors (fallback) ---
function getRandomColor() {
    const letters = '0123456789ABCDEF';
    let color = '#';
    for (let i = 0; i < 6; i++) {
        color += letters[Math.floor(Math.random() * 16)];
    }
    // Ensure high contrast / avoid very light colors if needed for readability
    // Example: return `hsl(${Math.random() * 360}, 80%, 50%)`;
    return color;
}
