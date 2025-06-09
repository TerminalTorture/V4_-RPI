const charts = window.charts; // Assuming this is not used or managed elsewhere

let sensorData = {}; // Store data per variable: { variableName: [{x: time, y: value}, ...], ... }

let isPaused = window.isPaused || false; // Use global pause state, default to false

window.socChartInstances = {}; // Store Chart.js instances for SOC meters
window.lineChartInstances = {}; // Store Chart.js instances for line chart GROUPS (key: groupName)
window.registerDatasetMapping = {}; // Maps reg.name to { chart: groupChartInstance, datasetIndex: number }
let allRegisterConfigs = []; // To store fetched register configurations
const INITIAL_HISTORY_MINUTES = 5; // Fetch last 5 minutes of data initially
const MAX_DATA_POINTS = INITIAL_HISTORY_MINUTES * 60; // Max data points to show on line charts (15 min at 2s interval = 450)

window.showLoginModal = function() {
    const modal = document.getElementById('loginModal');
    if (modal) {
        modal.classList.remove('hidden');
        modal.classList.add('flex'); // Ensure flex is added for visibility and centering
    }
};
window.closeLoginModal = function() {
    const modal = document.getElementById('loginModal');
    if (modal) {
        modal.classList.add('hidden');
        modal.classList.remove('flex'); // Remove flex when hiding
    }
};

function setRgbaAlpha(rgbaColor, alpha) {
    if (typeof rgbaColor === 'string' && rgbaColor.startsWith('rgba(')) {
        return rgbaColor.replace(/[^,]+(?=\))/, alpha.toString());
    }

    return 'rgba(75, 192, 192, 0.2)'; 
}

// Function to create an individual SOC meter chart
function createSocMeter(canvasId, socName, label) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
        console.error(`Canvas element with ID '${canvasId}' not found for SOC meter '${socName}'.`);
        return null;
    }
    // Destroy existing chart if it exists
    if (window.socChartInstances[socName] && typeof window.socChartInstances[socName].destroy === 'function') {
        window.socChartInstances[socName].destroy();
        // console.log(`Destroyed existing SOC meter for ${socName}`);
    }
    const ctx = canvas.getContext('2d');
    if (typeof Chart === 'undefined') {
        console.error('Chart.js is not loaded. SOC Meter cannot be initialized.');
        return null;
    }
    const meter = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: [label || 'SOC', 'Remaining'],
            datasets: [{
                data: [0, 100],
                backgroundColor: ['#4CAF50', '#E0E0E0'],
                borderWidth: 0
            }]
        },
        options: {
            cutout: '80%',
            responsive: false, // Crucial: Chart.js should use canvas attributes/style
            maintainAspectRatio: false, // Allow distortion if w/h attributes differ from CSS (they don't here)
            plugins: {
                legend: { display: false },
                tooltip: { enabled: false }
            },
            animation: { duration: 500 }
        }
    });
    window.socChartInstances[socName] = meter;
    return meter;
}

// Function to update an individual SOC meter's visual display and text value
function updateSocMeterDisplay(socName, value, unit = '%') {
    const chart = window.socChartInstances[socName];
    const numericValue = parseFloat(value); // Ensure value is a number

    if (!chart) {
        console.warn(`[Live Data] SOC chart instance for '${socName}' not found.`);
        // Attempt to find the canvas to see if it was ever created
        if (!document.getElementById(`${socName}_SocCanvas`)) {
            console.warn(`[Live Data] Canvas element '${socName}_SocCanvas' also not found for SOC meter '${socName}'.`);
        }
    } else {
        if (typeof numericValue === 'number' && !isNaN(numericValue)) {
            chart.data.datasets[0].data[0] = numericValue;
            chart.data.datasets[0].data[1] = 100 - numericValue; // Assuming 100 is max
            chart.update('none'); // 'none' for no animation, efficient for frequent updates
        } else {
            // console.warn(`Invalid value for SOC meter ${socName}: ${value}`);
            chart.data.datasets[0].data[0] = 0;
            chart.data.datasets[0].data[1] = 100;
            chart.update('none');
        }
    }

    const textElement = document.getElementById(`${socName}_SocValueText`);
    if (!textElement) {
        console.warn(`[Live Data] Text element '${socName}_SocValueText' not found for SOC meter '${socName}'.`);
    } else {
        if (typeof numericValue === 'number' && !isNaN(numericValue)) {
            textElement.textContent = `${numericValue.toFixed(1)}${unit}`;
        } else {
            textElement.textContent = 'N/A';
        }
    }
}

// Function to update an individual display value card
function updateDisplayValue(elementId, value, unit = '', scale = 1, defaultDecimals = 2) {
    const displayElement = document.getElementById(elementId);
    if (!displayElement) {
        console.warn(`[Live Data] UI element with ID '${elementId}' not found for display_value update.`);
        return;
    }
    if (displayElement) {
        const numericValue = parseFloat(value);
        if (value !== undefined && value !== null && !isNaN(numericValue)) {
            const scaledValue = numericValue * (scale || 1);
            // Use the provided defaultDecimals. This value is derived from register_config.yaml (reg.ui.decimals)
            // by the calling function (fetchAllLiveDataAndUpdateDisplays), or a sensible fallback if not specified there.
            let decimals = defaultDecimals;

            // For very small scales, ensure we show enough precision if the provided 'decimals' is too low.
            // This acts as a minimum precision guarantee for these specific cases.
            if (scale < 0.01 && decimals < 4) decimals = 4;
            if (scale < 0.001 && decimals < 5) decimals = 5;

            displayElement.textContent = `${scaledValue.toFixed(decimals)} ${unit}`;
        } else {
            displayElement.textContent = `N/A ${unit}`;
        }
    }
}

// Function to update a status display card
function updateStatusDisplayCard(regName, rawValue, statusMapping, label) {
    const cardId = `${regName}_StatusCard`;
    const valueElementId = `${regName}_StatusValue`;
    let card = document.getElementById(cardId);
    let valueElement = document.getElementById(valueElementId);

    if (!card) {
        console.warn(`[Live Data] Status card element with ID '${cardId}' not found for status_display '${regName}'.`);
        return;
    }
    if (!valueElement) {
        console.warn(`[Live Data] Value element with ID '${valueElementId}' not found for status_display '${regName}'.`);
        // Card might exist, but value part is missing. Still, can't update.
        return;
    }

    // Ensure rawValue is treated as an integer for status mapping lookup if it's a whole number float
    let statusKey;
    const parsedFloat = parseFloat(rawValue);
    if (!isNaN(parsedFloat) && Number.isInteger(parsedFloat)) {
        statusKey = String(parseInt(parsedFloat));
    } else {
        statusKey = String(rawValue); // Fallback for non-integer or already string values
    }
    
    if (statusMapping && statusMapping[statusKey]) {
        const statusInfo = statusMapping[statusKey];
        valueElement.textContent = statusInfo.text || 'Unknown Status';
        valueElement.style.color = statusInfo.color || 'inherit';
    } else {
        valueElement.textContent = 'N/A';
        valueElement.style.color = 'inherit';
        // console.warn(`No status mapping found for ${regName} with value ${rawValue}`);
    }
}

// Function to update a bitmask display card
function updateBitmaskDisplayCard(regName, rawValue, bitMapping, label) {
    const cardId = `${regName}_BitmaskCard`;
    const containerId = `${regName}_BitmaskValuesContainer`;
    let card = document.getElementById(cardId);
    let bitValuesContainer = document.getElementById(containerId);

    if (!card) {
        console.warn(`[Live Data] Bitmask card element with ID '${cardId}' not found for bitmask_display '${regName}'.`);
        return;
    }
    if (!bitValuesContainer) {
        console.warn(`[Live Data] Bit values container with ID '${containerId}' not found for bitmask_display '${regName}'.`);
        // Card might exist, but container part is missing. Still, can't update.
        return;
    }

    bitValuesContainer.innerHTML = ''; // Clear previous entries

    if (typeof rawValue !== 'number') {
        const naMessage = document.createElement('div');
        naMessage.textContent = 'Data N/A';
        bitValuesContainer.appendChild(naMessage);
        return;
    }

    for (const bitPosition in bitMapping) {
        if (!bitMapping.hasOwnProperty(bitPosition)) continue;

        const mappingConfig = bitMapping[bitPosition]; // Value for this bit key
        const bitIsSet = (rawValue >> parseInt(bitPosition)) & 1;
        const stateKey = bitIsSet ? '1' : '0';

        let displayNameForRule; // The label text for this bit's row
        let displayValueForRule; // The value text for this bit's row (e.g., "ON", "OFF", or descriptive state)

        if (typeof mappingConfig === 'string') {
            // Current/Old format: mappingConfig is the descriptive label string
            displayNameForRule = mappingConfig;
            displayValueForRule = bitIsSet ? 'ON' : 'OFF';
        } else if (typeof mappingConfig === 'object' && mappingConfig !== null && !Array.isArray(mappingConfig)) {
            // New format: mappingConfig is an object like {"0": "Text for state 0", "1": "Text for state 1"}
            // For the label, we'll use "Bit X" as a default. If you want more descriptive labels
            // for these new format entries, you'll need to adjust your register_config.yaml.
            displayNameForRule = `Bit ${bitPosition}`; 
            if (mappingConfig.hasOwnProperty(stateKey)) {
                displayValueForRule = mappingConfig[stateKey];
            } else {
                displayValueForRule = `Undefined state (${stateKey})`; // Fallback
            }
        } else {
            // Unsupported format for this bit position in the mapping
            displayNameForRule = `Bit ${bitPosition} (config error)`;
            displayValueForRule = bitIsSet ? 'ON' : 'OFF'; // Default display
        }

        const bitEntryDiv = document.createElement('div');
        bitEntryDiv.className = 'flex justify-between items-center text-xs';

        const labelSpan = document.createElement('span');
        labelSpan.className = 'font-medium text-on-surface-variant';
        labelSpan.textContent = `${displayNameForRule}:`; // Append colon

        const valueSpan = document.createElement('span');
        valueSpan.textContent = displayValueForRule;
        // Color is determined by the actual bit state (set or not set)
        valueSpan.className = bitIsSet ? 'text-green-600 font-semibold' : 'text-red-600 font-semibold';

        bitEntryDiv.appendChild(labelSpan);
        bitEntryDiv.appendChild(valueSpan);
        bitValuesContainer.appendChild(bitEntryDiv);
    }
}

// Function to fetch all live data and update displays
function fetchAllLiveDataAndUpdateDisplays() {
    if (window.isPaused || typeof isAuthenticated === 'undefined' || isAuthenticated === "false") {
        if (isAuthenticated === "false") {
            // console.log("User not authenticated. Skipping live data fetch.");
            // Optionally, redirect to login or show a message
            // For now, just ensure no further processing if not authenticated.
            if (document.getElementById('loginModal') && !document.getElementById('loginModal').classList.contains('hidden')) {
                // If login modal is already open, do nothing more here.
            } else if (typeof showLoginModal === 'function' && isAuthenticated === "false") {
                // console.log("Attempting to show login modal as user is not authenticated.");
                // showLoginModal(); // This might be too aggressive if called every second
            }
        }
        return;
    }

    const chartsNeedingUpdate = new Set(); // Collect unique chart instances to update once

    fetch('/api/live-data')
        .then(response => {
            if (!response.ok) {
                throw new Error(`Network response was not ok: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.error) {
                console.error('Error from live-data API:', data.error);
                return;
            }

            // Robust handling for the common timestamp of the data packet
            let commonTimestampForPacket;
            if (data.timestamp) {
                const parsedServerTime = new Date(data.timestamp);
                if (!isNaN(parsedServerTime.getTime())) {
                    commonTimestampForPacket = parsedServerTime;
                } else {
                    console.warn(`Invalid server timestamp in data packet: '${data.timestamp}'. Using client time as fallback.`);
                    commonTimestampForPacket = new Date(); // Fallback to client's current time
                }
            } else {
                // console.log("Server timestamp not provided in data packet. Using client time as fallback.");
                commonTimestampForPacket = new Date(); // Fallback if server timestamp is null/undefined/empty
            }

            allRegisterConfigs.forEach(reg => {
                // MODIFIED: Robust check for 'live' view (string or array)
                if (!reg.ui || !reg.ui.view) return; // Skip if no ui or view defined

                let shouldProcessForLiveView = false;
                if (Array.isArray(reg.ui.view)) {
                    shouldProcessForLiveView = reg.ui.view.includes('live');
                } else if (typeof reg.ui.view === 'string') {
                    shouldProcessForLiveView = reg.ui.view === 'live';
                }

                if (!shouldProcessForLiveView) return; // Skip if not for live view

                // Access sensor values from the nested data.data object
                const value = data.data ? data.data[reg.name] : undefined;
                const unit = reg.unit || '';
                // Set scale to 1 for all registers as API provides pre-scaled data.
                let scale = 1;

                const decimals = reg.ui.decimals !== undefined ? reg.ui.decimals : ((reg.scale && reg.scale.toString().includes('.')) ? reg.scale.toString().split('.')[1].length : 2); // Use reg.scale for decimals calculation if needed, but not for scaling value

                if (value === undefined) {
                    // Enhanced logging for missing data keys
                    if (data.data) {
                        console.warn(`[Live Data] No data received for register: '${reg.name}'. Available keys in API's 'data' object: [${Object.keys(data.data).join(', ')}]`);
                    } else {
                        console.warn(`[Live Data] No data received for register: '${reg.name}'. The API response did not contain a 'data' object or it was undefined.`);
                    }
                }

                const components = Array.isArray(reg.ui.component) ? reg.ui.component : [reg.ui.component];

                components.forEach(componentType => {
                    if (componentType === 'soc_meter') {
                        updateSocMeterDisplay(reg.name, value, unit);
                    } else if (componentType === 'line_chart') {
                        const mapping = window.registerDatasetMapping[reg.name];
                        if (!mapping) {
                            console.warn(`[Live Data] No dataset mapping found for line chart register: '${reg.name}'. Ensure it was configured for live view and UI created.`);
                        } else if (!mapping.chart) {
                            console.warn(`[Live Data] Chart instance is missing in dataset mapping for line chart register: '${reg.name}'.`);
                        } else if (!mapping.chart.data.datasets[mapping.datasetIndex]) {
                            console.warn(`[Live Data] Target dataset (index: ${mapping.datasetIndex}) not found in chart for line chart register: '${reg.name}'. Chart has ${mapping.chart.data.datasets.length} datasets.`);
                        } else {
                            const chartToUpdate = mapping.chart;
                            const datasetToUpdateIndex = mapping.datasetIndex;
                            const targetDataset = chartToUpdate.data.datasets[datasetToUpdateIndex];

                            // This check is technically redundant if the above checks pass, but good for explicitness.
                            // if (targetDataset) { // Already covered by checks above
                                const numericValue = parseFloat(value);
                                if (!isNaN(numericValue)) {
                                    const scaledValue = numericValue * scale;
                                    const newPointTimestamp = commonTimestampForPacket;

                                    targetDataset.data.push({ x: newPointTimestamp, y: scaledValue });

                                    const fifteenMinutesInMillis = INITIAL_HISTORY_MINUTES * 60 * 1000;
                                    const windowStartTimeLimit = newPointTimestamp.getTime() - fifteenMinutesInMillis;

                                    while (
                                        targetDataset.data.length > 0 &&
                                        targetDataset.data[0].x &&
                                        typeof targetDataset.data[0].x.getTime === 'function' &&
                                        !isNaN(targetDataset.data[0].x.getTime()) &&
                                        targetDataset.data[0].x.getTime() < windowStartTimeLimit
                                    ) {
                                        targetDataset.data.shift();
                                    }

                                    while (targetDataset.data.length > MAX_DATA_POINTS) {
                                        targetDataset.data.shift();
                                    }

                                    chartsNeedingUpdate.add(chartToUpdate);
                                } else {
                                    // console.warn(`Invalid data for line chart dataset ${reg.name}: ${value}`);
                                }
                            // } else { // Should not be reached if above checks are in place
                            //     console.error(`Dataset not found for ${reg.name} at index ${datasetToUpdateIndex} in chart for group ${reg.group}`);
                            // }
                        }
                    } else if (componentType === 'display_value') {
                        const elementId = `${reg.name}_DisplayValue`;
                        updateDisplayValue(elementId, value, unit, scale, decimals);
                    } else if (componentType === 'status_display') {
                        updateStatusDisplayCard(reg.name, value, reg.ui.status_mapping, reg.ui.label || reg.name);
                    } else if (componentType === 'bitmask_display') {
                        updateBitmaskDisplayCard(reg.name, value, reg.ui.bit_mapping, reg.ui.label || reg.name);
                    } else if (componentType === 'status_indicator') {
                        // Basic update for status_indicator: just show the raw value for now.
                        // More advanced logic (e.g., changing color/icon based on value) can be added here.
                        const elementId = `${reg.name}_StatusIndicator_Value`;
                        const displayElement = document.getElementById(elementId);
                        if (displayElement) {
                            displayElement.textContent = value !== undefined && value !== null ? `${value} ${unit}` : `N/A ${unit}`;
                        }
                    }
                });
            });

            // Update all modified charts once after all data processing for this interval is complete
            chartsNeedingUpdate.forEach(chart => {
                chart.update('none');
            });

        })
        .catch(error => {
            console.error('❌ Error fetching or processing live data:', error);
        });
}

// Function to reset zoom on all line charts
window.resetAllChartsZoom = function() {
    Object.values(window.lineChartInstances).forEach(chart => {
        if (chart && typeof chart.resetZoom === 'function') {
            chart.resetZoom();
        }
    });
    // SOC meters (doughnut) typically don't have zoom.
};

// Pause/Resume functionality
function togglePauseUpdates() {
    window.isPaused = !window.isPaused;
    const button = document.getElementById('pauseResumeButton');
    if (button) {
        button.textContent = window.isPaused ? 'Resume Updates' : 'Pause Updates';
        button.classList.toggle('bg-primary', !window.isPaused);
        button.classList.toggle('bg-secondary', window.isPaused);
        button.classList.toggle('text-on-primary', !window.isPaused);
        button.classList.toggle('text-on-secondary', window.isPaused);
    }
    if (!window.isPaused) {
        fetchAllLiveDataAndUpdateDisplays(); // Fetch immediately on resume
    }
    console.log(window.isPaused ? "Updates Paused" : "Updates Resumed");
}

// New function to fetch initial historical data for line charts
async function fetchInitialLineChartData(rangeMinutes, relevantConfigs) {
    console.log(`[HistData] Attempting to fetch initial historical data for the last ${rangeMinutes} minutes, covering ${relevantConfigs.length} relevant configurations.`);
    const initialDataMap = {};

    // Initialize initialDataMap for all relevant registers
    relevantConfigs.forEach(reg => {
        initialDataMap[reg.name] = [];
    });

    if (!relevantConfigs || relevantConfigs.length === 0) {
        console.log("[HistData] No relevant line chart configurations provided for historical data fetch. Returning empty map.");
        return initialDataMap;
    }

    const cacheBuster = new Date().getTime();
    const apiUrl = `/api/historical-data?range=${rangeMinutes}m&_cb=${cacheBuster}`;
    console.log(`[HistData] Calling API: ${apiUrl}`);

    try {
        const response = await fetch(apiUrl);
        if (!response.ok) {
            let errorBody = null;
            try {
                errorBody = await response.json();
            } catch (e) {
                // console.warn("[HistData] Could not parse JSON from error response body:", e);
            }
            const errorMsg = `[HistData] Historical data fetch failed: ${response.status} - ${errorBody ? JSON.stringify(errorBody) : response.statusText}`;
            console.error(errorMsg);
            return initialDataMap;
        }

        const apiResponseData = await response.json();
        console.log(`[HistData] API returned ${apiResponseData.length} records.`);

        if (apiResponseData.length > 0 && typeof apiResponseData[0] === 'object' && apiResponseData[0] !== null) {
            console.log("[HistData] Keys in the first historical record from API:", Object.keys(apiResponseData[0]));
        } else if (apiResponseData.length === 0) {
            console.warn("[HistData] API returned an empty array of records. No historical data to process.");
        }

        const timestampKey = 'timestamp';

        // Populate initialDataMap with all fetched data first
        apiResponseData.forEach(record => {
            const recordTimestampValue = record[timestampKey];
            if (recordTimestampValue === undefined) {
                return;
            }
            const recordDate = new Date(recordTimestampValue);
            if (isNaN(recordDate.getTime())) {
                return;
            }

            relevantConfigs.forEach(reg => {
                if (record[reg.name] !== undefined) {
                    const rawValue = record[reg.name];
                    const parsedValue = parseFloat(rawValue);
                    let pointToPushY = null;
                    if (rawValue === null) {
                        pointToPushY = null;
                    } else if (!isNaN(parsedValue)) {
                        const scale = reg.scale || 1;
                        pointToPushY = parsedValue * scale;
                    } else {
                        pointToPushY = null;
                    }
                    initialDataMap[reg.name].push({ x: recordDate, y: pointToPushY });
                }
            });
        });

        // Now, process each register's data in initialDataMap
        for (const regName in initialDataMap) {
            if (initialDataMap.hasOwnProperty(regName)) {
                let dataArray = initialDataMap[regName];
                if (!Array.isArray(dataArray) || dataArray.length === 0) {
                    continue;
                }

                dataArray.sort((a, b) => a.x.getTime() - b.x.getTime());

                // Define the 15-minute window based on client's current time
                const clientNow = new Date();
                const fifteenMinutesInMillis = INITIAL_HISTORY_MINUTES * 60 * 1000;
                const historyWindowEndTime = clientNow.getTime();
                const historyWindowStartTime = historyWindowEndTime - fifteenMinutesInMillis;
                
                // Filter points to be within this client-side defined window
                dataArray = dataArray.filter(point => {
                    const pointTime = point.x.getTime();
                    return pointTime >= historyWindowStartTime && pointTime <= historyWindowEndTime;
                });
                
                // If, after filtering, we still have too many points, take the most recent ones
                if (dataArray.length > MAX_DATA_POINTS) {
                    dataArray = dataArray.slice(-MAX_DATA_POINTS);
                }
                initialDataMap[regName] = dataArray;

                const isDebugTarget = regName === 'CL1_OCV' || regName === 'CL1_SOC'; // Example for debug
                if (isDebugTarget) {
                    console.log(`[HistData-Debug ${regName}] After client-side window filtering & MAX_DATA_POINTS, ${dataArray.length} points remain.`);
                }
            }
        }

    } catch (error) {
        console.error("[HistData] Critical error during fetchInitialLineChartData function execution:", error.message, error.stack);
    }
    return initialDataMap;
}


// Main setup on DOMContentLoaded
document.addEventListener('DOMContentLoaded', async function() {
    console.log("DOM Content Loaded. Initializing dynamic UI for grouped charts...");

    // Load settings from localStorage
    try {
        document.getElementById("unitName").textContent = localStorage.getItem("unitName") || "Unit: XX";
        document.getElementById("profileInfo").textContent = localStorage.getItem("profileInfo") || "10kW / 250kWh";
        document.getElementById("siteName").textContent = "Site: " + (localStorage.getItem("siteName") || "Singapore");
    } catch (e) {
        console.error("Error loading settings from localStorage:", e);
    }

    const cluster1SocMeterContainer = document.getElementById('cluster1SocMeterContainer'); // New container for CL1 SOC
    const cluster2SocMeterContainer = document.getElementById('cluster2SocMeterContainer'); // New container for CL2 SOC

    const cluster1StatusDisplayGrid = document.getElementById('cluster1StatusDisplayGrid'); // New grid for CL1
    const cluster2StatusDisplayGrid = document.getElementById('cluster2StatusDisplayGrid'); // New grid for CL2
    const systemStatusDisplayGrid = document.getElementById('systemStatusDisplayGrid'); // Added for system-level display values
    const liveChartsGrid = document.getElementById('liveChartsGrid');
    const pauseResumeBtn = document.getElementById('pauseResumeButton');
    const loadingSpinner = document.getElementById('loadingSpinner');

    if (loadingSpinner) loadingSpinner.classList.remove('hidden');

    if (pauseResumeBtn) {
        pauseResumeBtn.addEventListener('click', togglePauseUpdates);
        pauseResumeBtn.textContent = window.isPaused ? 'Resume Updates' : 'Pause Updates';
    }


    if (!cluster1SocMeterContainer) console.error("Cluster 1 SOC Meter Container (cluster1SocMeterContainer) not found!");
    if (!cluster2SocMeterContainer) console.error("Cluster 2 SOC Meter Container (cluster2SocMeterContainer) not found!");
    if (!cluster1StatusDisplayGrid) console.error("Cluster 1 Status Display Grid (cluster1StatusDisplayGrid) not found!");
    if (!cluster2StatusDisplayGrid) console.error("Cluster 2 Status Display Grid (cluster2StatusDisplayGrid) not found!");
    if (!systemStatusDisplayGrid) console.error("System Status Display Grid (systemStatusDisplayGrid) not found!"); // Added check
    if (!liveChartsGrid) console.error("Live Charts Grid (liveChartsGrid) not found!");

    // Clear any previous chart instances or mappings
    Object.values(window.lineChartInstances).forEach(chart => {
        if (chart && typeof chart.destroy === 'function') chart.destroy();
    });
    window.lineChartInstances = {};
    window.registerDatasetMapping = {};
    Object.values(window.socChartInstances).forEach(chart => {
        if (chart && typeof chart.destroy === 'function') chart.destroy();
    });
    window.socChartInstances = {};

    try {
        const response = await fetch('/api/registers/definitions');
        console.log('[DebugAuth] Fetch response status:', response.status);
        console.log('[DebugAuth] Fetch response.ok:', response.ok);
        console.log('[DebugAuth] Fetch response.url:', response.url);
        console.log('[DebugAuth] Fetch response.redirected:', response.redirected);

        const contentType = response.headers.get("Content-Type");
        console.log('[DebugAuth] Content-Type header from response.headers.get():', contentType);

        if (!response.ok) {
            const errorText = await response.text();
            // Added more detailed logging here as well
            console.error(`[DebugAuth] Fetch not OK. Status: ${response.status}, StatusText: ${response.statusText}, Redirected: ${response.redirected}, Final URL: ${response.url}`);
            if ((response.status === 401 || response.status === 403) && typeof showLoginModal === 'function') {
                console.log("[DebugAuth] Authentication error (401/403), showing login modal if possible.");
                showLoginModal();
            }
            throw new Error(`Failed to fetch register definitions (response not ok): ${response.statusText}. Response: ${errorText}`);
        }

        if (contentType && contentType.includes("text/html")) {
            console.info('[Auth] Authentication required. Please log in to load sensor definitions. Login modal displayed.');
            if (typeof showLoginModal === 'function' && (typeof isAuthenticated === 'undefined' || isAuthenticated === "false")) {
                showLoginModal();
            }
            // Always hide spinner and return if HTML was received, as we can't process definitions
            if (loadingSpinner) loadingSpinner.classList.add('hidden'); 
            return; // Gracefully stop processing definitions here
        } else {
            // This block is for when content type is NOT HTML (i.e., we expect JSON)
            // console.log('[DebugAuth] Condition (contentType && contentType.includes("text/html")) is FALSE. Proceeding to response.json().'); // Keeping other debug logs for now
            // console.log('[DebugAuth] contentType value was:', contentType);
            if (!contentType) {
                // console.warn('[DebugAuth] Content-Type header is missing or null. This might cause issues if HTML is returned without this header.');
            }
        }

        const responseData = await response.json();
        if (responseData && Array.isArray(responseData.registers)) {
            allRegisterConfigs = responseData.registers;
        } else if (Array.isArray(responseData)) {
            allRegisterConfigs = responseData;
        } else {
            console.error("Fetched register configurations is not an array and does not have a 'registers' array property. Actual data:", responseData);
            allRegisterConfigs = [];
            throw new Error('Register definitions are not in the expected format.');
        }
        console.log("Processed register configurations:", allRegisterConfigs);

        // Filter for line chart configs to fetch their initial data
        const lineChartConfigsForLiveView = allRegisterConfigs.filter(reg => {
            if (!(reg.ui && Array.isArray(reg.ui.view) && reg.ui.view.includes('live'))) {
                return false;
            }
            // Normalize reg.ui.component to an array to check for 'line_chart'
            const components = Array.isArray(reg.ui.component)
                               ? reg.ui.component
                               : (reg.ui.component ? [reg.ui.component] : []);
            return components.includes('line_chart');
        });

        let initialChartData = {};
        if (lineChartConfigsForLiveView.length > 0) {
            console.log("[DOMSetup] Requesting historical data for registers:", lineChartConfigsForLiveView.map(r => r.name)); // Log which registers are being fetched
            initialChartData = await fetchInitialLineChartData(INITIAL_HISTORY_MINUTES, lineChartConfigsForLiveView);
            // Log the number of points fetched for each register
            console.log("[DOMSetup] Fetched initialChartData (sensor: point_count):", JSON.stringify(Object.fromEntries(Object.entries(initialChartData).map(([k, v]) => [k, Array.isArray(v) ? v.length : 'N/A']))));
        }
        // console.log("Initial chart data fetched for line charts:", initialChartData);


        allRegisterConfigs.forEach(reg => {
            // MODIFIED: Robust check for 'live' view (string or array)
            if (!reg.ui || !reg.ui.view) return; // Skip if no ui or view defined

            let shouldProcessForLiveView = false;
            if (Array.isArray(reg.ui.view)) {
                shouldProcessForLiveView = reg.ui.view.includes('live');
            } else if (typeof reg.ui.view === 'string') {
                shouldProcessForLiveView = reg.ui.view === 'live';
            }

            if (!shouldProcessForLiveView) return; // Skip if not for live view

            const components = Array.isArray(reg.ui.component) ? reg.ui.component : [reg.ui.component];
            const displayName = reg.ui.label || reg.name;
            const unit = reg.unit || '';

            components.forEach(componentType => {
                if (componentType === 'soc_meter') {
                    const meterId = `${reg.name}_SocCanvas`;
                    const valueTextId = `${reg.name}_SocValueText`;
                    
                    // The md3-card container is now in the HTML. We just create the contents.
                    // const meterCard = document.createElement('div');
                    // meterCard.className = 'md3-card p-3 flex flex-col items-center justify-center bg-surface-container-lowest min-h-[170px] min-w-[140px] max-w-[190px]';
                    // Title for SOC meter card is now handled by the section title in HTML (already in the container)

                    const canvasContainer = document.createElement('div');
                    canvasContainer.className = 'relative w-32 h-32 flex items-center justify-center mt-2'; // Added mt-2 for spacing from title
                    // meterCard.appendChild(canvasContainer);

                    const canvas = document.createElement('canvas');
                    canvas.id = meterId;
                    canvas.width = 128;
                    canvas.height = 128;
                    canvas.style.width = '128px';
                    canvas.style.height = '128px';
                    canvas.style.maxWidth = '128px';
                    canvas.style.maxHeight = '128px';
                    canvas.style.display = 'block';
                    canvasContainer.appendChild(canvas);

                    const valueText = document.createElement('p');
                    valueText.id = valueTextId;
                    valueText.className = 'text-base font-semibold mt-1 text-primary';
                    valueText.textContent = 'N/A';
                    // meterCard.appendChild(valueText);

                    // Determine which SOC container to append to
                    let targetContainer = null;
                    if (reg.name === 'SOC1' || reg.name.startsWith('CL1') || (reg.group && reg.group.includes('Cluster 1'))) {
                        targetContainer = cluster1SocMeterContainer;
                    } else if (reg.name === 'SOC2' || reg.name.startsWith('CL2') || (reg.group && reg.group.includes('Cluster 2'))) {
                        targetContainer = cluster2SocMeterContainer;
                    } else {
                        // Default to Cluster 1 if not explicitly CL1 or CL2 and it's an SOC meter
                        console.warn(`SOC Meter ${reg.name} (group: ${reg.group}) does not explicitly belong to CL1 or CL2. Defaulting to Cluster 1 container.`);
                        targetContainer = cluster1SocMeterContainer;
                    }

                    if (targetContainer) {
                        // Clear previous content if any (e.g., during a hot reload/re-init)
                        // while (targetContainer.firstChild && targetContainer.firstChild.nodeName !== 'H3') {
                        //    targetContainer.removeChild(targetContainer.firstChild);
                        // }
                        // The H3 is already in the HTML, so we append after it or just append directly if structure is simple.
                        // For simplicity, assuming the container is ready for canvas and text.
                        targetContainer.appendChild(canvasContainer); // canvasContainer contains the canvas
                        targetContainer.appendChild(valueText);
                    } else {
                        console.warn(`Target container not found for SOC Meter ${reg.name}.`);
                    }

                    createSocMeter(meterId, reg.name, displayName); // displayName is still useful for the chart label itself
                } else if (componentType === 'line_chart' && liveChartsGrid) {
                    const groupName = reg.group || 'Uncategorized Charts';
                    const groupRegisters = allRegisterConfigs.filter(r => r.group === groupName && r.ui && Array.isArray(r.ui.component) && r.ui.component.includes('line_chart') && Array.isArray(r.ui.view) && r.ui.view.includes('live'));
                    const commonUnit = groupRegisters.length > 0 && groupRegisters[0].unit ? (groupRegisters[0].unit) : 'Value';
                    const yAxisTitle = `${groupName} (${commonUnit})`;

                    let groupChart = window.lineChartInstances[groupName];
                    let groupHasInitialData = false; // Flag to disable animation if any dataset in group has initial data

                    // Check if any dataset that will be part of this group has initial data
                    // This is a bit tricky as we build the group chart first, then add datasets.
                    // We can check if any reg in this group has data in initialChartData.
                    const registersInThisGroup = allRegisterConfigs.filter(r => r.group === groupName && lineChartConfigsForLiveView.includes(r));
                    if (registersInThisGroup.some(r => initialChartData[r.name] && initialChartData[r.name].length > 0)) {
                        groupHasInitialData = true;
                    }


                    if (!groupChart) {
                        const groupCard = document.createElement('div');
                        // Changed: Removed col-span-*, p-4. Added overflow-hidden. Matches historical.js card class more closely.
                        groupCard.className = 'md3-card bg-surface-container rounded-lg shadow mb-6 overflow-hidden'; 
                        
                        // Added: Title container and title element styled like historical.js
                        const groupTitleOuterContainer = document.createElement('div');
                        groupTitleOuterContainer.className = 'bg-primary-container p-4';
                        const groupTitleEl = document.createElement('h3');
                        groupTitleEl.className = 'text-on-primary-container font-medium'; 
                        groupTitleEl.textContent = groupName;
                        groupTitleOuterContainer.appendChild(groupTitleEl);
                        groupCard.appendChild(groupTitleOuterContainer);

                        // Changed: This div now handles padding and fixed height for the chart area, like historical.js
                        const chartDisplayArea = document.createElement('div');
                        chartDisplayArea.className = 'p-4 relative'; 
                        chartDisplayArea.style.height = '300px'; 
                        groupCard.appendChild(chartDisplayArea);

                        const canvas = document.createElement('canvas');
                        canvas.id = `${groupName.replace(/\s+/g, '_')}_GroupChartCanvas`;
                        chartDisplayArea.appendChild(canvas); // Canvas goes into the new chartDisplayArea
                        liveChartsGrid.appendChild(groupCard);

                        const ctx = canvas.getContext('2d');
                        groupChart = new Chart(ctx, {
                            type: 'line',
                            data: {
                                datasets: [] // Initialize with empty datasets, data will be added
                            },
                            options: {
                                responsive: true,
                                maintainAspectRatio: false,
                                animation: {
                                    // No animation if loading historical data initially, otherwise default (500ms)
                                    duration: groupHasInitialData ? 0 : 500 
                                },
                                scales: {
                                    x: {
                                        type: 'time',
                                        time: {
                                            unit: 'minute',
                                            tooltipFormat: 'Pp HH:mm:ss OOOO', // Display local time with offset in tooltip
                                            displayFormats: {
                                                second: 'HH:mm:ss',
                                                minute: 'HH:mm',
                                                hour: 'HH:mm'
                                            }
                                        },
                                        ticks: {
                                            maxRotation: 0,
                                            autoSkip: true,
                                            source: 'auto' // REMOVED COMMA: Callback is commented, so no trailing comma here
                                            // callback: function(value, index, ticks) {
                                            //     // 'value' is milliseconds since epoch. new Date(value) gives local time.
                                            //     return new Date(value).toLocaleTimeString(); // Example: Show local time string
                                        }, // Closes ticks
                                        title: { display: true, text: 'Time (Browser Local Time)' } // Clarify timezone
                                    }, // Closes x
                                    y: {
                                        beginAtZero: false,
                                        title: { display: true, text: yAxisTitle }
                                    }
                                },
                                plugins: {
                                    legend: { display: true, position: 'top' },
                                    tooltip: { mode: 'index', intersect: false },
                                    zoom: {
                                        pan: { enabled: true, mode: 'x' },
                                        zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'x' },
                                        limits: {
                                            x: { maxRange: INITIAL_HISTORY_MINUTES * 60 * 1000 } // Dynamically set to 5 minutes in milliseconds
                                        }
                                    }
                                }
                            }
                        });
                        window.lineChartInstances[groupName] = groupChart;
                    }

                    const chartColor = reg.ui.color || 'rgba(75, 192, 192, 1)';
                    const historicalDataForReg = initialChartData[reg.name] || [];
                    
                    console.log(`[DOMSetup] Register ${reg.name} (Group: ${groupName}): Using ${historicalDataForReg.length} historical points.`);

                    // Determine pointRadius: show points if few historical data, hide if many or live.
                    let pointRadiusForDataset = 1.5; // Default for live points as they come in
                    if (historicalDataForReg.length > 0) {
                        if (historicalDataForReg.length < 20) {
                            pointRadiusForDataset = 2; // Show points if few historical ones
                        } else if (historicalDataForReg.length < MAX_DATA_POINTS * 0.5) { // If less than half of max points, still show them a bit
                            pointRadiusForDataset = 1;
                        } else { // Many historical points
                            pointRadiusForDataset = 0.5; // Minimal points if many historical ones, or 0 to hide
                        }
                    }

                    const newDataset = {
                        label: displayName,
                        data: historicalDataForReg, // Use fetched historical data
                        borderColor: chartColor,
                        backgroundColor: setRgbaAlpha(chartColor, 0.2),
                        fill: false,
                        tension: 0.1,
                        pointRadius: pointRadiusForDataset,
                        borderWidth: 1.5
                    };
                    groupChart.data.datasets.push(newDataset);
                    window.registerDatasetMapping[reg.name] = {
                        chart: groupChart,
                        datasetIndex: groupChart.data.datasets.length - 1
                    };
                    groupChart.update('none');

                } else if (componentType === 'display_value') {
                    const displayId = `${reg.name}_DisplayValue`;
                    const card = document.createElement('div');
                    card.className = 'md3-card p-4 bg-surface-container low rounded-lg shadow';
                    const title = document.createElement('h5');
                    title.className = 'text-sm font-medium text-on-surface-variant mb-1';
                    title.textContent = displayName;
                    card.appendChild(title);
                    const valueDisplay = document.createElement('p');
                    valueDisplay.id = displayId;
                    valueDisplay.className = 'text-xl font-semibold text-primary';
                    valueDisplay.textContent = 'N/A';
                    card.appendChild(valueDisplay);

                    // Determine which grid to append to based on register name or group
                    if (reg.name.startsWith('CL1') || (reg.group && reg.group.includes('Cluster 1'))) {
                        if (cluster1StatusDisplayGrid) cluster1StatusDisplayGrid.appendChild(card);
                    } else if (reg.name.startsWith('CL2') || (reg.group && reg.group.includes('Cluster 2'))) {
                        if (cluster2StatusDisplayGrid) cluster2StatusDisplayGrid.appendChild(card);
                    } else {
                        // Fallback for items not explicitly CL1 or CL2 - append to systemStatusDisplayGrid
                        if (systemStatusDisplayGrid) {
                            systemStatusDisplayGrid.appendChild(card);
                        } else {
                            console.warn(`Display value ${reg.name} (group: ${reg.group}) could not be placed. System status grid not found.`);
                        }
                    }
                } else if (componentType === 'status_display') {
                    const cardId = `${reg.name}_StatusCard`;
                    const valueElementId = `${reg.name}_StatusValue`;
                    if (!document.getElementById(cardId)) { // Create card if it doesn't exist
                        const card = document.createElement('div');
                        card.id = cardId;
                        card.className = 'md3-card p-3 bg-surface-container-low rounded-lg shadow min-h-[80px] flex flex-col justify-center items-center';
                        
                        const title = document.createElement('h5');
                        title.className = 'text-xs font-medium text-on-surface-variant mb-1 truncate text-center';
                        title.textContent = displayName;
                        title.title = displayName; // Tooltip for full name if truncated
                        card.appendChild(title);
                        
                        const valueDisplay = document.createElement('p');
                        valueDisplay.id = valueElementId;
                        valueDisplay.className = 'text-lg font-semibold text-center'; // Color will be set by updater
                        valueDisplay.textContent = 'N/A';
                        card.appendChild(valueDisplay);

                        // Determine which grid to append to
                        if (reg.name.startsWith('CL1') || (reg.group && reg.group.includes('Cluster 1'))) {
                            if (cluster1StatusDisplayGrid) cluster1StatusDisplayGrid.appendChild(card);
                        } else if (reg.name.startsWith('CL2') || (reg.group && reg.group.includes('Cluster 2'))) {
                            if (cluster2StatusDisplayGrid) cluster2StatusDisplayGrid.appendChild(card);
                        } else {
                            if (systemStatusDisplayGrid) systemStatusDisplayGrid.appendChild(card);
                            else console.warn(`Status display ${reg.name} could not be placed. System status grid not found.`);
                        }
                    }
                    // Actual update will happen in fetchAllLiveDataAndUpdateDisplays
                    // updateStatusDisplayCard(reg.name, initialChartData[reg.name], reg.ui.status_mapping, displayName);

                } else if (componentType === 'bitmask_display') {
                    const cardId = `${reg.name}_BitmaskCard`;
                    const containerId = `${reg.name}_BitmaskValuesContainer`;
                    if (!document.getElementById(cardId)) { // Create card if it doesn't exist
                        const card = document.createElement('div');
                        card.id = cardId;
                        card.className = 'md3-card p-3 bg-surface-container-low rounded-lg shadow';

                        const title = document.createElement('h5');
                        title.className = 'text-xs font-medium text-on-surface-variant mb-2 truncate';
                        title.textContent = displayName;
                        title.title = displayName;
                        card.appendChild(title);

                        const bitValuesContainer = document.createElement('div');
                        bitValuesContainer.id = containerId;
                        bitValuesContainer.className = 'space-y-1'; // Styles for bit entries
                        card.appendChild(bitValuesContainer);

                        // Determine which grid to append to
                        if (reg.name.startsWith('CL1') || (reg.group && reg.group.includes('Cluster 1'))) {
                            if (cluster1StatusDisplayGrid) cluster1StatusDisplayGrid.appendChild(card);
                        } else if (reg.name.startsWith('CL2') || (reg.group && reg.group.includes('Cluster 2'))) {
                            if (cluster2StatusDisplayGrid) cluster2StatusDisplayGrid.appendChild(card);
                        } else {
                            if (systemStatusDisplayGrid) systemStatusDisplayGrid.appendChild(card);
                            else console.warn(`Bitmask display ${reg.name} could not be placed. System status grid not found.`);
                        }
                    }
                    // Actual update will happen in fetchAllLiveDataAndUpdateDisplays
                    // updateBitmaskDisplayCard(reg.name, initialChartData[reg.name], reg.ui.bit_mapping, displayName);
                } else if (componentType === 'status_indicator') {
                    const cardId = `${reg.name}_StatusIndicatorCard`;
                    const valueElementId = `${reg.name}_StatusIndicator_Value`;
                    if (!document.getElementById(cardId)) { // Create card if it doesn't exist
                        const card = document.createElement('div');
                        card.id = cardId;
                        // Basic styling, similar to status_display but can be simpler
                        card.className = 'md3-card p-3 bg-surface-container-low rounded-lg shadow min-h-[80px] flex flex-col justify-center items-center';
                        
                        const title = document.createElement('h5');
                        title.className = 'text-xs font-medium text-on-surface-variant mb-1 truncate text-center';
                        title.textContent = displayName;
                        title.title = displayName; // Tooltip for full name if truncated
                        card.appendChild(title);
                        
                        const valueDisplay = document.createElement('p');
                        valueDisplay.id = valueElementId;
                        valueDisplay.className = 'text-lg font-semibold text-center'; // Styling can be adjusted
                        valueDisplay.textContent = 'N/A';
                        card.appendChild(valueDisplay);

                        // Determine which grid to append to (similar to status_display)
                        if (reg.name.startsWith('CL1') || (reg.group && reg.group.includes('Cluster 1'))) {
                            if (cluster1StatusDisplayGrid) cluster1StatusDisplayGrid.appendChild(card);
                        } else if (reg.name.startsWith('CL2') || (reg.group && reg.group.includes('Cluster 2'))) {
                            if (cluster2StatusDisplayGrid) cluster2StatusDisplayGrid.appendChild(card);
                        } else {
                            if (systemStatusDisplayGrid) systemStatusDisplayGrid.appendChild(card);
                            else console.warn(`Status indicator ${reg.name} could not be placed. System status grid not found.`);
                        }
                    }
                }
            });
        });

        // After the main loop that processes allRegisterConfigs and populates charts
        // Ensure all charts reset zoom and update to reflect initial data correctly
        Object.values(window.lineChartInstances).forEach(chart => {
            if (chart && typeof chart.resetZoom === 'function') {
                chart.resetZoom(); 
                chart.update('none'); // 'none' prevents animation during this update
            }
        });

        if (loadingSpinner) loadingSpinner.classList.add('hidden');

        // START: Added visibility checks
        const cl1SocContainer = document.getElementById('cluster1SocMeterContainer');
        const cl2SocContainer = document.getElementById('cluster2SocMeterContainer');
        if (cl1SocContainer && !cl1SocContainer.querySelector('canvas')) {
            cl1SocContainer.classList.add('hidden');
        }
        if (cl2SocContainer && !cl2SocContainer.querySelector('canvas')) {
            cl2SocContainer.classList.add('hidden');
        }

        const cl1StatusGrid = document.getElementById('cluster1StatusDisplayGrid');
        const cl2StatusGrid = document.getElementById('cluster2StatusDisplayGrid');
        const sysStatusGrid = document.getElementById('systemStatusDisplayGrid');

        let cl1StatusParentHidden = false;
        let cl2StatusParentHidden = false;
        let sysStatusParentHidden = false;

        if (cl1StatusGrid && cl1StatusGrid.childElementCount === 0) {
            // Assuming the parent div of the grid is the one with the title we want to hide
            const cl1ParentDiv = cl1StatusGrid.closest('div.grid > div'); // Adjust selector if HTML structure is different
            if (cl1ParentDiv && cl1ParentDiv.querySelector('h3')?.textContent.includes('Cluster 1')) {
                 cl1ParentDiv.classList.add('hidden');
                 cl1StatusParentHidden = true;
            } else { // Fallback to hide just the grid if specific parent isn't found
                cl1StatusGrid.classList.add('hidden');
                cl1StatusParentHidden = true; // Still consider it hidden for section logic
            }
        }
        if (cl2StatusGrid && cl2StatusGrid.childElementCount === 0) {
            const cl2ParentDiv = cl2StatusGrid.closest('div.grid > div'); // Adjust selector
             if (cl2ParentDiv && cl2ParentDiv.querySelector('h3')?.textContent.includes('Cluster 2')) {
                 cl2ParentDiv.classList.add('hidden');
                 cl2StatusParentHidden = true;
            } else {
                cl2StatusGrid.classList.add('hidden');
                cl2StatusParentHidden = true;
            }
        }
        if (sysStatusGrid && sysStatusGrid.childElementCount === 0) {
            const sysParentDiv = sysStatusGrid.parentElement; // System grid is directly in a div with a title
            if (sysParentDiv && sysParentDiv.querySelector('h3')?.textContent.includes('System Status')) {
                sysParentDiv.classList.add('hidden');
                sysStatusParentHidden = true;
            } else {
                 sysStatusGrid.classList.add('hidden');
                 sysStatusParentHidden = true;
            }
        }
        
        const liveStatusSection = document.getElementById('liveStatusDisplaySection');
        if (liveStatusSection && cl1StatusParentHidden && cl2StatusParentHidden && sysStatusParentHidden) {
            liveStatusSection.classList.add('hidden');
        }

        const liveChartsGridEl = document.getElementById('liveChartsGrid');
        const liveChartsSectionEl = document.getElementById('liveChartsSection');
        if (liveChartsGridEl && liveChartsSectionEl && liveChartsGridEl.childElementCount === 0) {
            liveChartsSectionEl.classList.add('hidden');
        }
        // END: Added visibility checks

    } catch (error) {
        console.error("Error during initial setup:", error);
        if (loadingSpinner) loadingSpinner.classList.add('hidden');
        const body = document.querySelector('body');
        if (body) {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'fixed top-0 left-0 right-0 bg-red-500 text-white p-4 text-center z-[100]';
            errorDiv.textContent = `Initialization Error: ${error.message}. Please check console.`;
            body.prepend(errorDiv);
            setTimeout(() => errorDiv.remove(), 10000);
        }
    }

    if (typeof isAuthenticated !== 'undefined' && isAuthenticated !== "false") {
        console.log("User is authenticated. Starting live data updates.");
        fetchAllLiveDataAndUpdateDisplays(); // Initial fetch
        // Corrected: Call the updater function for status and bitmask displays within the main fetch loop
        // The card creation logic is in DOMContentLoaded, data update logic in fetchAllLiveDataAndUpdateDisplays
        // The logic in fetchAllLiveDataAndUpdateDisplays needs to call these for registers.
        allRegisterConfigs.forEach(reg => {
            if (!reg.ui || !Array.isArray(reg.ui.view) || !reg.ui.view.includes('live')) {
                return;
            }
            const components = Array.isArray(reg.ui.component) ? reg.ui.component : [reg.ui.component];
            components.forEach(componentType => {
                if (componentType === 'status_display') {
                    // The initial call to updateStatusDisplayCard in DOMContentLoaded might use stale 'data'
                    // We ensure it's called correctly within fetchAllLiveDataAndUpdateDisplays as well.
                    // No, the creation is in DOMContentLoaded. The update is in fetchAllLiveDataAndUpdateDisplays.
                    // The logic in fetchAllLiveDataAndUpdateDisplays needs to call these for registers.
                } else if (componentType === 'bitmask_display') {
                    // Similar to status_display, updates should be primarily driven by fetchAllLiveDataAndUpdateDisplays
                } else if (componentType === 'status_indicator') {
                    // Similar to status_display, updates should be primarily driven by fetchAllLiveDataAndUpdateDisplays
                }
            });
        });
        setInterval(fetchAllLiveDataAndUpdateDisplays, 1000); // Regular updates
    } else {
        console.log("User not authenticated. Live updates will not start.");
        if (typeof showLoginModal === 'function') {
            const modal = document.getElementById('loginModal');
            if (modal && modal.classList.contains('hidden')) {
                // showLoginModal(); 
            }
        }
    }

    const hamburgerMenu = document.getElementById('hamburger-menu');
    const sidebar = document.getElementById('sidebar');
    const sidebarOverlay = document.getElementById('sidebar-overlay');

    if (hamburgerMenu && sidebar && sidebarOverlay) {
        hamburgerMenu.addEventListener('click', () => {
            sidebar.classList.toggle('-translate-x-full');
            sidebarOverlay.classList.toggle('hidden');
        });
        sidebarOverlay.addEventListener('click', () => {
            sidebar.classList.add('-translate-x-full');
            sidebarOverlay.classList.add('hidden');
        });
    } else {
        console.warn("Sidebar elements not fully found for hamburger menu.");
    }
});
