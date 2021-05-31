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

export default getBadgeType;
