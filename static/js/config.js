window.registerDefinitions = null; // Placeholder to store fetched definitions
window.charts = {}; // Keep chart instances accessible
window.isPaused = false; // Keep pause state

// Function to save modbus configuration settings
function saveConfig() {
    console.log("Saving modbus configuration...");
    
    // Get values from the configuration inputs
    const ipAddressInput = document.getElementById("ipAddress");
    const portNumberInput = document.getElementById("portNumber");
    
    if (!ipAddressInput || !portNumberInput) {
        console.error("Configuration input elements not found");
        alert("Configuration form elements not found!");
        return;
    }
    
    const ipAddress = ipAddressInput.value.trim();
    const portNumber = portNumberInput.value.trim();
    
    // Basic validation
    if (!ipAddress) {
        alert("Please enter an IP address");
        ipAddressInput.focus();
        return;
    }
    
    if (!portNumber) {
        alert("Please enter a port number");
        portNumberInput.focus();
        return;
    }
    
    // Validate IP address format (basic validation)
    const ipRegex = /^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$/;
    if (!ipRegex.test(ipAddress)) {
        alert("Please enter a valid IP address (e.g., 192.168.1.1)");
        ipAddressInput.focus();
        return;
    }
    
    // Validate port number
    const port = parseInt(portNumber);
    if (isNaN(port) || port < 1 || port > 65535) {
        alert("Please enter a valid port number (1-65535)");
        portNumberInput.focus();
        return;
    }
    
    // Save to localStorage
    localStorage.setItem("modbusIpAddress", ipAddress);
    localStorage.setItem("modbusPortNumber", portNumber);
    
    // Show success message
    alert("Configuration saved successfully!");
    
    console.log(`Configuration saved - IP: ${ipAddress}, Port: ${portNumber}`);
}

// Function to load saved configuration on page load
function loadSavedConfig() {
    const ipAddressInput = document.getElementById("ipAddress");
    const portNumberInput = document.getElementById("portNumber");
    
    if (ipAddressInput && portNumberInput) {
        // Load saved values or set defaults
        ipAddressInput.value = localStorage.getItem("modbusIpAddress") || "";
        portNumberInput.value = localStorage.getItem("modbusPortNumber") || "502";
        
        console.log("Saved configuration loaded");
    }
}

// Load configuration when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    loadSavedConfig();
});

console.log("config.js loaded - Register definitions will be fetched dynamically.");
