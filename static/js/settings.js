document.addEventListener("DOMContentLoaded", () => {
    // Load saved settings from localStorage
    const unitNameInput = document.getElementById("unitName");
    const profileInfoInput = document.getElementById("profileInfo");
    const siteNameInput = document.getElementById("siteName");

    // Set input values from localStorage or set defaults
    unitNameInput.value = localStorage.getItem("unitName") || "Unit: XX";
    profileInfoInput.value = localStorage.getItem("profileInfo") || "100kW / 500kWh";
    siteNameInput.value = localStorage.getItem("siteName") || "Singapore";
});

window.toggleSidebar = function() {
    const sidebar = document.getElementById("sidebar");
    sidebar.style.width = sidebar.style.width === "250px" ? "0" : "250px";
  };
  

function saveSettings() {
    const loadingSpinner = document.getElementById('loadingSpinner');
    // Check if the spinner element exists before trying to access its style
    if (loadingSpinner) {
        loadingSpinner.style.display = 'block';
    } else {
        console.error("Element with ID 'loadingSpinner' not found.");
        // Optionally, handle the case where the spinner doesn't exist,
        // maybe by skipping the visual feedback or logging an error.
    }

    // Get values from inputs
    const unitName = document.getElementById("unitName").value;
    const profileInfo = document.getElementById("profileInfo").value;
    const siteName = document.getElementById("siteName").value;

    // Save to localStorage
    localStorage.setItem("unitName", unitName);
    localStorage.setItem("profileInfo", profileInfo);
    localStorage.setItem("siteName", siteName);

    setTimeout(() => {
        // Also check here if the spinner exists before hiding it
        if (loadingSpinner) {
            loadingSpinner.style.display = 'none';
        }
        alert('Settings saved successfully!');
    }, 2000);
}
