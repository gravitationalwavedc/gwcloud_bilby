const getBadgeType = (name) => {
    const variants = {
        'Production Run': 'success',
        'Bad Run': 'danger',
        'Review Requested': 'secondary',
        'Reviewed': 'info',
        'Preferred': 'warning'
    };

    return variants[name];
};

const getStatusType = (name) => {
    const variants = {
        'Completed': 'text-success',
        'Error': 'text-danger',
        'Running': 'text-info',
        'Unknown': 'text-muted'
    }

    return variants[name]
}

export {
    getBadgeType,
    getStatusType
};
