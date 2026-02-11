// Function to send an AJAX request
function sendAjaxRequest(url, method, data, onSuccess, onError) {
    fetch(url, {
        method: method,
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
    })
    .then(response => response.json())
    .then(data => onSuccess(data))
    .catch((error) => {
        console.error('Error:', error);
        if (onError) onError(error);
    });
}

// Example of using the sendAjaxRequest function
// Assuming you have buttons or elements with data attributes for picker IDs
document.querySelectorAll('.picker-button').forEach(button => {
    button.addEventListener('click', function() {
        const pickerId = this.getAttribute('data-picker-id');
        sendAjaxRequest('/start_pick', 'POST', { pickerId: pickerId },
            (data) => {
                // Handle successful response
                console.log(data);
                // Update the DOM based on the response
            },
            (error) => {
                // Handle error
                console.error('Failed to start pick:', error);
            });
    });
});
document.addEventListener("DOMContentLoaded", function() {
    const tbody = document.getElementById('picksTableBody')});

