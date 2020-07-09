import {expect} from "@jest/globals";
import { 
    checkForErrors,
    isLongerThan,
    isShorterThan,
    isANumber,
    isAPositiveNumber,
    isAnInteger,
    isAPositiveInteger,
    isLargerThan,
    isSmallerThan,
    isNotEmpty,
    hasNoneFalse,
    isValidJobName
} from "../errors";

// Just testing all the error functions

const testString = 'test'
const testStringLong = 'test string'
const emptyishString = ' '
const allowedName = 'AaBbCcDdEeFfGgHhIiJjKkLlMmNnOoPpQqRrSsTtUuVvWwXxYyZz1234567890-_'
const disallowedName = 'We cannot use punctuation, with the exception of underscores and hyphens.' 

const testInt = 1
const testIntLarge = 10
const testIntNegative = -1

const testFloat = 1.0
const testFloatNegative = -1.0

const boolArrayWithTrue = [true, false]
const boolArrayWithoutTrue = [false, false]

describe('isLongerThan', () => {
    it('raises no error for string longer than threshold', () => {
        const { errors } = isLongerThan(5)({data: testStringLong, errors: []})
        expect(errors).toHaveLength(0);
    })
    
    it('raises one error for string shorter than threshold', () => {
        const { errors } = isLongerThan(5)({data: testString, errors: []})
        expect(errors).toHaveLength(1);
    })
})

describe('isShorterThan', () => {
    it('raises no error for string shorter than threshold', () => {
        const { errors } = isShorterThan(5)({data: testString, errors: []})
        expect(errors).toHaveLength(0);
    })
    
    it('raises one error for string shorter than threshold', () => {
        const { errors } = isShorterThan(5)({data: testStringLong, errors: []})
        expect(errors).toHaveLength(1);
    })
})

describe('isANumber', () => {
    it('raises no error for integer, or string that can be converted to integer', () => {
        let { errors } = isANumber({data: testInt, errors: []})
        expect(errors).toHaveLength(0);

        ({ errors } = isANumber({data: testInt.toString(), errors: []}))
        expect(errors).toHaveLength(0);
    })
    
    it('raises no error for float, or string that can be converted to float', () => {
        let { errors } = isANumber({data: testFloat, errors: []})
        expect(errors).toHaveLength(0);
        
        ({ errors } = isANumber({data: testFloat.toString(), errors: []}))
        expect(errors).toHaveLength(0);
    })

    it('raises one error for other strings', () => {
        const { errors } = isANumber({data: testString, errors: []})
        expect(errors).toHaveLength(1);
    })
})

describe('isAPositiveNumber', () => {
    it('raises no error for integer, or string that can be converted to integer', () => {
        let { errors } = isAPositiveNumber({data: testInt, errors: []})
        expect(errors).toHaveLength(0);

        ({ errors } = isAPositiveNumber({data: testInt.toString(), errors: []}))
        expect(errors).toHaveLength(0);
    })
    
    it('raises no error for float, or string that can be converted to float', () => {
        let { errors } = isAPositiveNumber({data: testFloat, errors: []})
        expect(errors).toHaveLength(0);
        
        ({ errors } = isAPositiveNumber({data: testFloat.toString(), errors: []}))
        expect(errors).toHaveLength(0);
    })

    it('raises one error for other strings', () => {
        const { errors } = isAPositiveNumber({data: testString, errors: []})
        expect(errors).toHaveLength(1);
    })

    it('raises one error for negative numbers', () => {
        let { errors } = isAPositiveNumber({data: testIntNegative, errors: []})
        expect(errors).toHaveLength(1);

        ({ errors } = isAPositiveNumber({data: testFloatNegative, errors: []}))
        expect(errors).toHaveLength(1);
    })
})

describe('isAnInteger', () => {
    it('raises no error for integer, or string that can be converted to integer', () => {
        let { errors } = isAnInteger({data: testInt, errors: []})
        expect(errors).toHaveLength(0);

        ({ errors } = isAnInteger({data: testInt.toString(), errors: []}))
        expect(errors).toHaveLength(0);
    })
    
    it('raises one error for float, or string that can be converted to float', () => {
        let { errors } = isAnInteger({data: testFloat, errors: []})
        expect(errors).toHaveLength(0);
        
        ({ errors } = isAnInteger({data: testFloat.toString(), errors: []}))
        expect(errors).toHaveLength(0);
    })

    it('raises one error for other strings', () => {
        const { errors } = isAnInteger({data: testString, errors: []})
        expect(errors).toHaveLength(1);
    })
})

describe('isAPositiveInteger', () => {
    it('raises no error for integer, or string that can be converted to integer', () => {
        let { errors } = isAPositiveInteger({data: testInt, errors: []})
        expect(errors).toHaveLength(0);

        ({ errors } = isAPositiveInteger({data: testInt.toString(), errors: []}))
        expect(errors).toHaveLength(0);
    })
    
    it('raises one error for float, or string that can be converted to float', () => {
        let { errors } = isAPositiveInteger({data: testFloat, errors: []})
        expect(errors).toHaveLength(0);
        
        ({ errors } = isAPositiveInteger({data: testFloat.toString(), errors: []}))
        expect(errors).toHaveLength(0);
    })

    it('raises one error for other strings', () => {
        const { errors } = isAPositiveInteger({data: testString, errors: []})
        expect(errors).toHaveLength(1);
    })

    it('raises one error for negative integer', () => {
        const { errors } = isAPositiveInteger({data: testIntNegative, errors: []})
        expect(errors).toHaveLength(1);
    })
})

describe('isLargerThan', () => {
    it('raises no error if data is smaller than threshold', () => {
        const { errors } = isLargerThan(testInt, 'placeholder')({data: testIntLarge, errors: []})
        expect(errors).toHaveLength(0);
    })
    
    it('raises an error if threshold is smaller than data', () => {
        const { errors } = isLargerThan(testIntLarge, 'placeholder')({data: testInt, errors: []})
        expect(errors).toHaveLength(1);
    })
})

describe('isSmallerThan', () => {
    it('raises no error if data is smaller than threshold', () => {
        const { errors } = isSmallerThan(testIntLarge, 'placeholder')({data: testInt, errors: []})
        expect(errors).toHaveLength(0);
    })
    
    it('raises an error if threshold is smaller than data', () => {
        const { errors } = isSmallerThan(testInt, 'placeholder')({data: testIntLarge, errors: []})
        expect(errors).toHaveLength(1);
    })
})

describe('isNotEmpty', () => {
    it('raises no error if string has anything other than whitespace', () => {
        const { errors } = isNotEmpty({data: testString, errors: []})
        expect(errors).toHaveLength(0);
    })
    
    it('raises an error if string is empty or contains only whitespace', () => {
        const { errors } = isNotEmpty({data: emptyishString, errors: []})
        expect(errors).toHaveLength(1);
    })
})

describe('hasNoneFalse', () => {
    it('raises no error if input list has at least one true value', () => {
        const { errors } = hasNoneFalse(boolArrayWithTrue)({data: false, errors: []})
        expect(errors).toHaveLength(0);
    })

    it('raises no error if input list has only false values, but data is true', () => {
        const { errors } = hasNoneFalse(boolArrayWithoutTrue)({data: true, errors: []})
        expect(errors).toHaveLength(0);
    })

    it('raises an error if input list has only false values, and data is false', () => {
        const { errors } = hasNoneFalse(boolArrayWithoutTrue)({data: false, errors: []})
        expect(errors).toHaveLength(1);
    })
})

describe('isValidJobName', () => {
    it('raises no error if name contains only valid characters', () => {
        const { errors } = isValidJobName({data: allowedName, errors: []})
        expect(errors).toHaveLength(0);
    })

    it('raises an error if name contains at least one invalid character', () => {
        const { errors } = isValidJobName({data: disallowedName, errors: []})
        expect(errors).toHaveLength(1);
    })
})

describe('checkForErrors', () => {
    it('creates an array with multiple error messages from each error test', () => {
        const errors = checkForErrors(isShorterThan(5), isNotEmpty, isANumber, isValidJobName)(disallowedName)
        expect(errors).toHaveLength(3); // Should check all of the above errors except for isNotEmpty
    })
})
