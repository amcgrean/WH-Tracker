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

function setupResponsiveSidebar() {
    const body = document.body;
    const openButton = document.getElementById('sidebarToggleButton');
    const closeButton = document.getElementById('sidebarCloseButton');
    const overlay = document.getElementById('appSidebarOverlay');
    const sidebar = document.getElementById('appSidebar');

    if (!openButton || !sidebar) {
        return;
    }

    const closeSidebar = () => {
        body.classList.remove('sidebar-open');
        openButton.setAttribute('aria-expanded', 'false');
    };

    const openSidebar = () => {
        body.classList.add('sidebar-open');
        openButton.setAttribute('aria-expanded', 'true');
    };

    openButton.addEventListener('click', () => {
        if (window.innerWidth >= 992) {
            return;
        }
        if (body.classList.contains('sidebar-open')) {
            closeSidebar();
        } else {
            openSidebar();
        }
    });

    if (closeButton) {
        closeButton.addEventListener('click', closeSidebar);
    }

    if (overlay) {
        overlay.addEventListener('click', closeSidebar);
    }

    sidebar.querySelectorAll('a').forEach((link) => {
        link.addEventListener('click', () => {
            if (window.innerWidth < 992) {
                closeSidebar();
            }
        });
    });

    window.addEventListener('resize', () => {
        if (window.innerWidth >= 992) {
            closeSidebar();
        }
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            closeSidebar();
        }
    });
}

// Example of using the sendAjaxRequest function
// Assuming you have buttons or elements with data attributes for picker IDs
document.querySelectorAll('.picker-button').forEach(button => {
    button.addEventListener('click', function () {
        const pickerId = this.getAttribute('data-picker-id');
        sendAjaxRequest('/start_pick', 'POST', { pickerId: pickerId },
            (data) => {
                console.log(data);
            },
            (error) => {
                console.error('Failed to start pick:', error);
            });
    });
});

document.addEventListener('DOMContentLoaded', function () {
    setupResponsiveSidebar();

    const tbody = document.getElementById('picksTableBody');
    if (!tbody) return;
    // picksTableBody is populated by page-specific scripts where needed
});
