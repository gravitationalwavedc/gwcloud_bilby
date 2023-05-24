const jobTypes = {
    0: 'NORMAL',
    1: 'UPLOADED',
    2: 'GWOSC'
};

export function getJobType(jobTypeCode) {

    // Make sure that the code is within the range of known codes.
    if (jobTypeCode > (jobTypes.length - 1)) {
        return undefined;
    }

    return jobTypes[jobTypeCode];
}
