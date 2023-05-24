import { getJobType } from '../jobHelpers';

describe('job helpers functions', () => {

    it('should return the correct job type', () => {
        expect.hasAssertions();
        expect(getJobType(0)).toBe('NORMAL');
        expect(getJobType(1)).toBe('UPLOADED');
        expect(getJobType(2)).toBe('GWOSC');
    });

    it('should return error if not a known job type', () => {
        expect.hasAssertions();
        expect(() => getJobType(30)).toThrow('Incorrect JobType!');
        expect(() => getJobType(-1)).toThrow('Incorrect JobType!');
    });
});
