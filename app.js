document.addEventListener('DOMContentLoaded', function() {
    console.log("Dashboard script loaded successfully");
    
    // DOM Elements - Main Views (Only try to access if they exist)
    const cameraView = document.getElementById('camera-view');
    const reviewView = document.getElementById('review-view');
    const loadingView = document.getElementById('loading-view');
    const resultsView = document.getElementById('results-view');
    
    // DOM Elements - Controls
    const captureBtn = document.getElementById('captureBtn');
    const retakeBtn = document.getElementById('retakeBtn');
    const analyzeBtn = document.getElementById('analyzeBtn');
    const newScanBtn = document.getElementById('new-scan-btn');
    const saveResultsBtn = document.getElementById('save-results-btn');
    
    // DOM Elements - Images
    const reviewImage = document.getElementById('review-image');
    const resultImage = document.getElementById('result-image');
    
    // DOM Elements - Loading
    const loadingSteps = document.querySelectorAll('.loading-step');
    
    // DOM Elements - Results
    const statusIndicator = document.getElementById('status-indicator');
    const statusIcon = statusIndicator ? statusIndicator.querySelector('.status-icon') : null;
    const statusText = statusIndicator ? statusIndicator.querySelector('.status-text') : null;
    const primaryIssue = document.getElementById('primary-issue');
    const detectionCounts = document.getElementById('detection-counts');
    const recommendationsList = document.getElementById('recommendations-list');
    
    // Pi Status Elements
    const piStatusIndicator = document.getElementById('pi-status');
    let piStatusIcon = null;
    let piStatusText = null;
    let piStatusDescription = null;
    
    if (piStatusIndicator) {
        console.log("Found Pi status indicator");
        piStatusIcon = piStatusIndicator.querySelector('.pi-status-icon i');
        piStatusText = piStatusIndicator.querySelector('.pi-status-text h4');
        piStatusDescription = piStatusIndicator.querySelector('.pi-status-text p');
    }
    
    // Current captured image tracking
    let currentImageFilename = null;
    let currentRequestId = null;
    let currentAnalysisData = null;
    
    // Check if we're on the dashboard page
    const isDashboard = document.querySelector('.dashboard-container') !== null;
    console.log("Is dashboard page:", isDashboard);
    
    // Function to check Pi connection status for dashboard
    function checkPiStatus() {
        if (!piStatusIndicator) {
            console.log("No Pi status indicator found");
            return; // Exit if indicator isn't present
        }
        
        console.log("Checking Pi status...");
        
        fetch('/api/pi-status')
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                console.log("Pi status response:", data);
                
                // Add pulse animation when the status changes
                piStatusIndicator.classList.add('pi-status-update');
                
                // Remove animation after it completes
                setTimeout(() => {
                    piStatusIndicator.classList.remove('pi-status-update');
                }, 500);
                
                // Update the status indicator
                if (data.connected) {
                    piStatusIcon.parentElement.classList.remove('pi-disconnected');
                    piStatusIcon.parentElement.classList.add('pi-connected');
                    piStatusText.textContent = 'Raspberry Pi Zero 2 W: Connected';
                    piStatusDescription.textContent = 'Your toothbrush tracking device is online and sending data.';
                } else {
                    piStatusIcon.parentElement.classList.remove('pi-connected');
                    piStatusIcon.parentElement.classList.add('pi-disconnected');
                    piStatusText.textContent = 'Raspberry Pi Zero 2 W: Not Connected';
                    piStatusDescription.textContent = 'Connect your device to track brushing habits.';
                }
            })
            .catch(error => {
                console.error('Error checking Pi status:', error);
                
                // Show error state in the indicator
                piStatusIcon.parentElement.classList.remove('pi-connected');
                piStatusIcon.parentElement.classList.add('pi-disconnected');
                piStatusText.textContent = 'Raspberry Pi Zero 2 W: Status Unknown';
                piStatusDescription.textContent = 'Could not determine device status. Please try again later.';
            });
    }
    
    // If on dashboard, set up Pi status checking
    if (isDashboard && piStatusIndicator) {
        // Check Pi status on page load
        checkPiStatus();
        
        // Check for Pi connection status updates every 30 seconds
        setInterval(checkPiStatus, 30000);
    }
    
    // Event Listeners for camera functionality - only set if elements exist
    if (captureBtn) captureBtn.addEventListener('click', captureImage);
    if (retakeBtn) retakeBtn.addEventListener('click', retakePhoto);
    if (analyzeBtn) analyzeBtn.addEventListener('click', analyzePhoto);
    if (newScanBtn) newScanBtn.addEventListener('click', resetToCamera);
    
    // Add event listener for save results button if it exists
    if (saveResultsBtn) {
        saveResultsBtn.addEventListener('click', saveResults);
    }
    
    // Setup event listeners for any delete buttons on the page
    document.querySelectorAll('.btn-delete').forEach(button => {
        button.addEventListener('click', function() {
            const scanId = this.getAttribute('data-scan-id');
            confirmDelete(scanId);
        });
    });
    
    // Dashboard-specific functionality
    function confirmDelete(scanId) {
        if (confirm('Are you sure you want to delete this scan? This cannot be undone.')) {
            window.location.href = `/delete-scan/${scanId}`;
        }
    }
    
    // Functions for camera/scanning functionality
    function captureImage() {
        // Show loading indicator during capture
        if (cameraView) cameraView.classList.add('hidden');
        if (loadingView) loadingView.classList.remove('hidden');
        if (reviewView) reviewView.classList.add('hidden');
        if (resultsView) resultsView.classList.add('hidden');
        
        // Reset loading steps
        resetLoadingSteps();
        updateLoadingStep(0, "Requesting capture...");
        
        // Queue a capture request
        fetch('/capture-only', {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                currentRequestId = data.request_id;
                updateLoadingStep(1, "Waiting for camera...");
                
                // Wait for the Pi to process (give it time to poll and capture)
                setTimeout(checkForLatestImage, 3000);
            } else {
                throw new Error(data.message || 'Failed to queue capture request');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Failed to capture image: ' + error.message);
            
            // Return to camera view on error
            if (loadingView) loadingView.classList.add('hidden');
            if (cameraView) cameraView.classList.remove('hidden');
        });
    }
    
    function checkForLatestImage() {
        updateLoadingStep(2, "Checking for image...");
        
        fetch('/get-latest-image')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // Image is available
                currentImageFilename = data.filename;
                if (reviewImage) reviewImage.src = `/uploads/${data.filename}?t=${new Date().getTime()}`;
                
                // Show review screen
                if (loadingView) loadingView.classList.add('hidden');
                if (reviewView) reviewView.classList.remove('hidden');
            } else if (data.status === 'waiting') {
                // Still waiting for image, check again
                setTimeout(checkForLatestImage, 2000);
            } else {
                throw new Error(data.message || 'Failed to get image');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            
            // If we're still waiting for the image, try again
            if (error.message.includes('No completed captures') || 
                error.message.includes('No images found')) {
                setTimeout(checkForLatestImage, 2000);
                return;
            }
            
            alert('Failed to get captured image: ' + error.message);
            
            // Return to camera view on error
            if (loadingView) loadingView.classList.add('hidden');
            if (cameraView) cameraView.classList.remove('hidden');
        });
    }
    
    function retakePhoto() {
        // Go back to camera view
        if (reviewView) reviewView.classList.add('hidden');
        if (cameraView) cameraView.classList.remove('hidden');
        
        // Reset current image
        currentImageFilename = null;
    }
    
    function analyzePhoto() {
        if (!currentImageFilename) {
            alert('No image available for analysis');
            return;
        }
    
        if (reviewView) reviewView.classList.add('hidden');
        if (loadingView) loadingView.classList.remove('hidden');
    
        resetLoadingSteps();
        updateLoadingStep(0, "Preparing image...");
    
        // Get the image from the server
        fetch(`/uploads/${currentImageFilename}`)
            .then(res => res.blob())
            .then(blob => {
                const formData = new FormData();
                formData.append('image', blob, currentImageFilename);
    
                updateLoadingStep(1, "Sending to Gemini...");
    
                return fetch('/analyze-image', {
                    method: 'POST',
                    body: formData
                });
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Server responded with status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                updateLoadingStep(2, "Processing Gemini results...");
                console.log("Received data from server:", data);
    
                if (data && data.response) {
                    // Save the response for display and later use
                    currentAnalysisData = {
                        analysis: data.response,
                        filename: currentImageFilename
                    };
    
                    displayResults(currentAnalysisData);
    
                    if (loadingView) loadingView.classList.add('hidden');
                    if (resultsView) resultsView.classList.remove('hidden');
                } else if (data && data.error) {
                    throw new Error(data.error);
                } else {
                    throw new Error("Invalid response from Gemini");
                }
            })
            .catch(error => {
                console.error('Error during analysis:', error);
                alert("Analysis failed: " + error.message);
                if (loadingView) loadingView.classList.add('hidden');
                if (reviewView) reviewView.classList.remove('hidden');
            });
    }

    
    function fetchAnalysisResults() {
        updateLoadingStep(2, "Retrieving results...");
        
        fetch('/get-analysis')
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to get results');
            }
            return response.json();
        })
        .then(data => {
            if (data.status === 'success') {
                const analysis = data.data; // ðŸ‘ˆ Extract actual analysis
        
                // Display predictions
                const predictionContainer = document.getElementById('condition-results');
                predictionContainer.innerHTML = '';
                analysis.predictions.forEach(p => {
                    const item = document.createElement('li');
                    item.textContent = `Class: ${p.class}, Confidence: ${p.confidence.toFixed(2)}, Box: [${p.box_2d.join(', ')}]`;
                    predictionContainer.appendChild(item);
                });
        
                // Display recommendations
                const recommendationContainer = document.getElementById('recommendation-results');
                recommendationContainer.innerHTML = '';
                analysis.recommendations.forEach(r => {
                    const recItem = document.createElement('li');
                    recItem.textContent = r;
                    recommendationContainer.appendChild(recItem);
                });
        
                // Show results view
                if (loadingView) loadingView.classList.add('hidden');
                if (resultsView) resultsView.classList.remove('hidden');
            } else {
                throw new Error(data.message || 'Analysis failed');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            
            // If the server is still processing, try again
            if (error.message.includes('No analysis results found')) {
                setTimeout(fetchAnalysisResults, 2000);
                return;
            }
            
            alert('Failed to get analysis results: ' + error.message);
            
            // Return to review view on error
            if (loadingView) loadingView.classList.add('hidden');
            if (reviewView) reviewView.classList.remove('hidden');
        });
    }

    
    function resetLoadingSteps() {
        if (!loadingSteps || loadingSteps.length === 0) return;
        loadingSteps.forEach(step => {
            step.classList.remove('active', 'completed');
        });
    }
    
    function updateLoadingStep(stepIndex, message) {
        if (!loadingSteps || loadingSteps.length === 0) return;
        loadingSteps.forEach((step, index) => {
            if (index < stepIndex) {
                step.classList.remove('active');
                step.classList.add('completed');
            } else if (index === stepIndex) {
                step.classList.add('active');
                step.classList.remove('completed');
                if (message) {
                    step.textContent = message;
                }
            } else {
                step.classList.remove('active', 'completed');
            }
        });
    }
    
    // Update the display results function to ensure bounding boxes are drawn at the right time
function displayResults(data) {
    console.log("Data for display:", data);
    
    // Check if elements exist before attempting to use them
    if (!statusIndicator || !primaryIssue || !detectionCounts || !recommendationsList) {
        console.warn("Results view elements not found");
        return;
    }
    
    // Check if data structure is valid
    if (!data || !data.analysis) {
        console.error("Invalid data format:", data);
        alert("Failed to get proper analysis data from server");
        return;
    }
    
    // Extract analysis data
    const analysis = data.analysis;
    
    // Show the image
    if (resultImage) {
        // Set a new onload handler before changing src
        resultImage.onload = function() {
            console.log("Result image loaded, natural size:", resultImage.naturalWidth, "x", resultImage.naturalHeight);
            
            // Ensure predictions exist
            if (analysis.predictions && analysis.predictions.length > 0) {
                console.log("Drawing bounding boxes for", analysis.predictions.length, "predictions");
                // Draw bounding boxes after the image has loaded
                setTimeout(() => {
                    drawBoundingBoxes(analysis.predictions);
                }, 100); // Small delay to ensure image dimensions are available
            } else {
                console.log("No predictions to display bounding boxes for");
            }
        };
        
        // Update the image source
        resultImage.src = `/uploads/${data.filename}?t=${new Date().getTime()}`;
    }
    
    // Set status indicator with proper null checks
    if (statusIcon) statusIcon.className = 'fas';
    
    // Default values if missing
    const status = analysis.status || "Unknown";
    const primaryIssueText = analysis.primary_issue || "No specific issues detected";
    
    // Update status indicator
    switch(status) {
        case 'Good':
            if (statusIcon) statusIcon.classList.add('fa-check-circle');
            if (statusText) statusText.textContent = 'Good';
            if (statusIndicator) statusIndicator.className = 'status-indicator status-good';
            break;
        case 'Needs improvement':
            if (statusIcon) statusIcon.classList.add('fa-exclamation-triangle');
            if (statusText) statusText.textContent = 'Needs Improvement';
            if (statusIndicator) statusIndicator.className = 'status-indicator status-warning';
            break;
        case 'Attention needed':
            if (statusIcon) statusIcon.classList.add('fa-exclamation-circle');
            if (statusText) statusText.textContent = 'Attention Needed';
            if (statusIndicator) statusIndicator.className = 'status-indicator status-danger';
            break;
        default:
            if (statusIcon) statusIcon.classList.add('fa-question-circle');
            if (statusText) statusText.textContent = 'Uncertain';
            if (statusIndicator) statusIndicator.className = 'status-indicator status-unknown';
    }
    
    // Set primary issue
    if (primaryIssue) primaryIssue.textContent = primaryIssueText;
    
    // Display detection counts with null checks
    if (detectionCounts) {
        detectionCounts.innerHTML = '';
        
        if (analysis.detection_counts) {
            Object.entries(analysis.detection_counts).forEach(([className, count]) => {
                // Skip if count is zero
                if (count === 0) return;
                
                // Create count item
                const itemDiv = document.createElement('div');
                itemDiv.className = 'detection-item';
                
                // Set styles based on condition type
                let iconClass, itemClass;
                switch(className) {
                    case 'healthy':
                        iconClass = 'fa-smile';
                        itemClass = 'detection-healthy';
                        break;
                    case 'plaque':
                        iconClass = 'fa-bacteria';
                        itemClass = 'detection-plaque';
                        break;
                    case 'caries':
                        iconClass = 'fa-tooth';
                        itemClass = 'detection-caries';
                        break;
                    default:
                        iconClass = 'fa-question';
                        itemClass = '';
                }
                
                itemDiv.classList.add(itemClass);
                
                // Build item content
                itemDiv.innerHTML = `
                    <div class="detection-count">${count}</div>
                    <div class="detection-icon"><i class="fas ${iconClass}"></i></div>
                    <div class="detection-label">${className.charAt(0).toUpperCase() + className.slice(1)}</div>
                    ${analysis.confidences && analysis.confidences[className] ? 
                      `<div class="detection-confidence">${Math.round(analysis.confidences[className])}% confidence</div>` : ''}
                `;
                
                detectionCounts.appendChild(itemDiv);
            });
        } else {
            detectionCounts.innerHTML = '<div class="no-detections">No detections available</div>';
        }
    }
    
    // Display recommendations
    if (recommendationsList) {
        recommendationsList.innerHTML = '';
        
        if (analysis.recommendations && analysis.recommendations.length > 0) {
            analysis.recommendations.forEach(recommendation => {
                const li = document.createElement('li');
                li.textContent = recommendation;
                recommendationsList.appendChild(li);
            });
        } else {
            recommendationsList.innerHTML = '<li>No specific recommendations available</li>';
        }
    }
}
    
function drawBoundingBoxes(predictions) {
    const image = document.getElementById('result-image');
    const canvas = document.getElementById('annotation-canvas');
    
    if (!image || !canvas || !predictions || predictions.length === 0) {
        console.log("Missing elements for drawing bounding boxes or no predictions");
        return;
    }

    console.log("Drawing bounding boxes for predictions:", predictions);
    const ctx = canvas.getContext('2d');

    // Wait for image to load if necessary
    if (!image.complete) {
        image.onload = () => drawBoundingBoxes(predictions);
        return;
    }

    // Resize canvas to match image dimensions exactly
    canvas.width = image.clientWidth;
    canvas.height = image.clientHeight;
    
    // Clear any previous drawings
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw each prediction box
    predictions.forEach((pred) => {
        // IMPORTANT: Check the coordinate format and rearrange if needed
        // Gemini may be returning [y0, x0, y1, x1] when we need [x0, y0, x1, y1]
        // Let's try the correct order based on your screenshot
        
        // Original: const [y0, x0, y1, x1] = pred.box_2d;
        const [x0, y0, x1, y1] = pred.box_2d; // Try this coordinate order
        
        // Calculate the scaling factors
        const scaleX = canvas.width / image.naturalWidth;
        const scaleY = canvas.height / image.naturalHeight;
        
        // Apply scaling to coordinates
        const left = x0 * scaleX;
        const top = y0 * scaleY;
        const width = (x1 - x0) * scaleX;
        const height = (y1 - y0) * scaleY;

        // Set different colors for different conditions
        let strokeColor = "red";
        if (pred.class.includes("healthy")) {
            strokeColor = "green";
        } else if (pred.class.includes("plaque")) {
            strokeColor = "orange";
        }

        // Draw rectangle with thicker border
        ctx.strokeStyle = strokeColor;
        ctx.lineWidth = 3;
        ctx.strokeRect(left, top, width, height);

        // Draw label with clear background
        const label = `${pred.class} (${Math.round(pred.confidence * 100)}%)`;
        ctx.font = "bold 14px Arial";
        const textMetrics = ctx.measureText(label);
        const textWidth = textMetrics.width;
        
        // Create background for text
        ctx.fillStyle = strokeColor;
        ctx.globalAlpha = 0.8;
        ctx.fillRect(left, top - 20, textWidth + 8, 20);
        ctx.globalAlpha = 1.0;
        
        // Add text
        ctx.fillStyle = "white";
        ctx.fillText(label, left + 4, top - 5);
    });
}    

    function resetToCamera() {
        // Clear current capture
        currentImageFilename = null;
        currentRequestId = null;
        
        // Reset views
        if (resultsView) resultsView.classList.add('hidden');
        if (reviewView) reviewView.classList.add('hidden');
        if (loadingView) loadingView.classList.add('hidden');
        if (cameraView) cameraView.classList.remove('hidden');
        
        // Reset status elements
        if (statusIndicator) statusIndicator.className = 'status-indicator';
        if (primaryIssue) primaryIssue.textContent = '';
        if (detectionCounts) detectionCounts.innerHTML = '';
        if (recommendationsList) recommendationsList.innerHTML = '';
    }
    
    function displayRecommendations(recommendations) {
    	const container = document.getElementById('recommendations');
    	if (!container) return;

   	container.innerHTML = '';
    	recommendations.forEach(rec => {
        const li = document.createElement('li');
        li.textContent = rec;
        container.appendChild(li);
    });
}

    function displayDetections(predictions) {
    	const canvas = document.getElementById('resultCanvas');
    	const ctx = canvas.getContext('2d');
    	const image = new Image();
    	image.src = '/uploads/' + currentImageFilename;

    	image.onload = () => {
        canvas.width = image.width;
        canvas.height = image.height;
        ctx.drawImage(image, 0, 0);

        predictions.forEach(det => {
            const [y0, x0, y1, x1] = det.box_2d;
            ctx.beginPath();
            ctx.rect(x0, y0, x1 - x0, y1 - y0);
            ctx.lineWidth = 2;
            ctx.strokeStyle = det.class === 'caries' ? 'red' :
                              det.class === 'plaque' ? 'orange' : 'green';
            ctx.stroke();
            ctx.font = "16px Arial";
            ctx.fillStyle = ctx.strokeStyle;
            ctx.fillText(`${det.class} (${Math.round(det.confidence * 100)}%)`, x0, y0 - 5);
        });
    };
}

    function saveResults() {
        // Can't save without analysis data
        if (!currentAnalysisData) {
            alert('No analysis data available to save');
            return;
        }
        
        // Send the request to save scan
        fetch('/save-scan', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                filename: currentImageFilename,
                analysis: currentAnalysisData.analysis
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                alert('Scan saved to your profile!');
                // Option to go to dashboard
                if (confirm('View your saved scans on your dashboard?')) {
                    window.location.href = '/dashboard';
                }
            } else {
                throw new Error(data.message || 'Failed to save scan');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Failed to save scan: ' + error.message);
        });
    }
})