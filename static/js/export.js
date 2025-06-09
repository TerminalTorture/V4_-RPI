document.addEventListener("DOMContentLoaded", function () {
    console.log("✅ export.js loaded successfully!");

    // ✅ Get elements safely
    const downloadCsvButton = document.getElementById("downloadCsvButton");
    const download30DaysButton = document.getElementById("download30Days");
    const downloadRange = document.getElementById("downloadRange");
    const customDateInputs = document.getElementById("customDateInputs");
    const variableCheckboxes = document.getElementById("variableCheckboxes");

    // ✅ Check if elements exist before using them
    if (!downloadCsvButton) {
        console.error("❌ Download button not found in export.js");
        return;
    }

    // Check auth status from variables set in the template
    const isAuthenticated = (typeof window.isAuthenticated !== 'undefined' && window.isAuthenticated === "true");
    const isAdmin = (typeof window.isAdminUser !== 'undefined' && window.isAdminUser === "true");
    
    console.log(`Auth status: ${isAuthenticated ? 'Logged in' : 'Not logged in'}, Admin: ${isAdmin ? 'Yes' : 'No'}`);

    // ✅ Function to format timestamps correctly
    function formatTimestamp(input) {
        if (!input) return null;
        input = input.replace("T", " "); // Convert 'YYYY-MM-DDTHH:MM' -> 'YYYY-MM-DD HH:MM'
        return input.length === 16 ? input + ":00" : input; // Ensure seconds are included
    }

    // ✅ Function to fetch and download CSV
    function fetchAndDownloadCSV(range, start = null, end = null) {
        const selectedVars = Array.from(document.querySelectorAll(".variable-selection input:checked"))
            .map(input => input.value);

        // Add the /api prefix to make it consistent with your other endpoints
        let url = `/api/historical-data/export?range=${range}`;
        if (range === "custom" && start && end) url += `&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`;
        if (selectedVars.length > 0) url += `&variables=${selectedVars.join(",")}`;

        console.log(`📥 Fetching data: ${url}`);

        fetch(url)
            .then(response => {
                if (!response.ok) throw new Error(`HTTP Error: ${response.status}`);
                return response.blob();
            })
                        .then(blob => {
                const link = document.createElement("a");
                link.href = window.URL.createObjectURL(blob);
                link.download = "sensor_data.csv";
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            })
            .catch(error => console.error("❌ Error exporting CSV:", error));
    }

    if (!isAuthenticated || !isAdmin) {
        // Non-admin user handling
        downloadCsvButton.addEventListener("click", function() {
            alert("Admin access required to download data. Please log in with an administrative account.");
            // Redirect to login page
            window.location.href = "/login";
        });
        
        if (download30DaysButton) {
            download30DaysButton.addEventListener("click", function() {
                alert("Admin access required to download data. Please log in with an administrative account.");
                window.location.href = "/login";
            });
        }
    } else {
        // Only load these elements and set up functionality for admins
        if (download30DaysButton && downloadRange && customDateInputs && variableCheckboxes) {
            // ✅ Fetch available variables and populate checkboxes
            fetch("/api/registers/definitions")
                .then(response => {
                    if (!response.ok) throw new Error(`HTTP Error: ${response.status} fetching register definitions`);
                    return response.json();
                })
                .then(definitionsResponse => {
                    if (!definitionsResponse || !Array.isArray(definitionsResponse.registers)) {
                        console.error("❌ Invalid format for register definitions:", definitionsResponse);
                        variableCheckboxes.innerHTML = "<p class='text-red-500'>Could not load variables.</p>";
                        return;
                    }
                    const variables = definitionsResponse.registers.map(reg => reg.name);
                    
                    variableCheckboxes.innerHTML = ""; // Clear previous content
                    variables.forEach(variable => {
                        if (!variable) return; // Skip if variable name is undefined or empty
                        let checkboxContainer = document.createElement("div");
                        checkboxContainer.classList.add("checkbox-container", "flex", "items-center", "mb-1");

                        let checkbox = document.createElement("input");
                        checkbox.type = "checkbox";
                        checkbox.value = variable;
                        checkbox.checked = true; // Default: all selected
                        checkbox.id = `var-${variable.replace(/\W/g, '_')}`; // Sanitize ID
                        checkbox.classList.add("form-checkbox", "h-4", "w-4", "text-primary", "border-gray-300", "rounded", "focus:ring-primary");

                        let label = document.createElement("label");
                        label.htmlFor = checkbox.id;
                        label.innerText = variable;
                        label.classList.add("ml-2", "text-sm", "text-on-surface");

                        checkboxContainer.appendChild(checkbox);
                        checkboxContainer.appendChild(label);
                        variableCheckboxes.appendChild(checkboxContainer);
                    });
                })
                .catch(error => {
                    console.error("❌ Error fetching or processing register definitions for export variables:", error);
                    if (variableCheckboxes) {
                        variableCheckboxes.innerHTML = "<p class='text-red-500'>Error loading variables.</p>";
                    }
                });

            // ✅ Show custom date inputs when 'Custom' is selected
            downloadRange.addEventListener("change", function () {
                customDateInputs.style.display = (this.value === "custom") ? "block" : "none";
            });

            // ✅ Handle "Download CSV" Button with selected time range & variables
            downloadCsvButton.addEventListener("click", function () {
                const range = downloadRange.value;
                let start = formatTimestamp(document.getElementById("customStartDate").value);
                let end = formatTimestamp(document.getElementById("customEndDate").value);

                if (range === "custom" && (!start || !end)) {
                    alert("⚠️ Please select both start and end dates!");
                    return;
                }

                console.log(`📥 Downloading data with range: ${range}, start: ${start}, end: ${end}`);
                fetchAndDownloadCSV(range, start, end);
            });

            // Add handler for 30-day button
            download30DaysButton.addEventListener("click", function() {
                console.log("📥 Downloading last 30 days of data...");
                fetchAndDownloadCSV("30d");
            });
        } else {
            // Protected download for admin, simpler version
            downloadCsvButton.addEventListener("click", function () {
                fetch('/api/protected-download')
                    .then(response => {
                        if (!response.ok) {
                            if (response.status === 403) {
                                throw new Error("Access denied. Admin privileges required.");
                            }
                            throw new Error(`Error: ${response.status}`);
                        }
                        return response.blob();
                    })
                    .then(blob => {
                        const link = document.createElement("a");
                        link.href = window.URL.createObjectURL(blob);
                        link.download = "historical_data.csv";
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                    })
                    .catch(error => {
                        console.error("❌ Error downloading CSV:", error);
                        alert(error.message);
                    });
            });
        }
    }
});



