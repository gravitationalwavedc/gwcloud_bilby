const jobTypes = {
    0: 'NORMAL',
    1: 'UPLOADED',
    2: 'GWOSC'
};

export function getJobType(jobTypeCode) {
    if (!(jobTypeCode in jobTypes)) {
        throw new Error(`Incorrect JobType! ${jobTypeCode} is not a known jobType. Known job types are ${jobTypes}.`);
    }

    return jobTypes[jobTypeCode];
}
