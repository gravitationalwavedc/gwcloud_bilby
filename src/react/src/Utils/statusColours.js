const statusColours = {
    0: '', // Draft
    10: 'warning', // Pending
    20: 'warning', // Submitting
    30: 'warning', // Submitted
    40: 'warning', // Queued
    50: 'info', // Running
    60: 'info', // Cancelling
    70: 'error', // Cancelled
    80: 'info', // Deleting
    90: 'error', // Deleted
    400: 'error', // Error
    401: 'error', // Wall time exceeded
    402: 'error', // Out of memory
    500: 'success', // Complete
}

export default statusColours;