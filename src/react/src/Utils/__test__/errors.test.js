import {expect} from "@jest/globals";
import { 
    checkForErrors,
    longerThan,
    shorterThan,
    isNumber,
    smallerThan,
    notEmpty,
    noneFalse,
    validJobName 
} from "../errors";

// Just testing all the error functions

let testString = 'test'
let testStringLong = 'test string'
let emptyishString = ' '
let allowedName = 'AaBbCcDdEeFfGgHhIiJjKkLlMmNnOoPpQqRrSsTtUuVvWwXxYyZz1234567890-_'
let disallowedName = 'We cannot use punctuation, with the exception of underscores and hyphens.' 

let testInt = 1
let testIntLarge = 10

let testFloat = 1.0

let boolArrayWithTrue = [true, false]
let boolArrayWithoutTrue = [false, false]

describe('longerThan', () => {
    it('raises no error for string longer than threshold', () => {
        const { errors } = longerThan(5)({data: testStringLong, errors: []})
        expect(errors).toHaveLength(0);
    })
    
    it('raises one error for string shorter than threshold', () => {
        const { errors } = longerThan(5)({data: testString, errors: []})
        expect(errors).toHaveLength(1);
    })
})

describe('shorterThan', () => {
    it('raises no error for string shorter than threshold', () => {
        const { errors } = shorterThan(5)({data: testString, errors: []})
        expect(errors).toHaveLength(0);
    })
    
    it('raises one error for string shorter than threshold', () => {
        const { errors } = shorterThan(5)({data: testStringLong, errors: []})
        expect(errors).toHaveLength(1);
    })
})

describe('isNumber', () => {
    it('raises no error for integer, or string that can be converted to integer', () => {
        let { errors } = isNumber({data: testInt, errors: []})
        expect(errors).toHaveLength(0);

        ({ errors } = isNumber({data: testInt.toString(), errors: []}))
        expect(errors).toHaveLength(0);
    })
    
    it('raises no error for float, or string that can be converted to integer', () => {
        let { errors } = isNumber({data: testFloat, errors: []})
        expect(errors).toHaveLength(0);
        
        ({ errors } = isNumber({data: testFloat.toString(), errors: []}))
        expect(errors).toHaveLength(0);
    })

    it('raises one error for other strings', () => {
        const { errors } = isNumber({data: testString, errors: []})
        expect(errors).toHaveLength(1);
    })
})

describe('smallerThan', () => {
    it('raises no error if data is smaller than threshold', () => {
        let { errors } = smallerThan(testIntLarge, 'placeholder')({data: testInt, errors: []})
        expect(errors).toHaveLength(0);
    })
    
    it('raises an error if threshold is smaller than data', () => {
        let { errors } = smallerThan(testInt, 'placeholder')({data: testIntLarge, errors: []})
        expect(errors).toHaveLength(1);
    })
})

describe('notEmpty', () => {
    it('raises no error if string has anything other than whitespace', () => {
        let { errors } = notEmpty({data: testString, errors: []})
        expect(errors).toHaveLength(0);
    })
    
    it('raises an error if string is empty or contains only whitespace', () => {
        let { errors } = notEmpty({data: emptyishString, errors: []})
        expect(errors).toHaveLength(1);
    })
})

describe('noneFalse', () => {
    it('raises no error if input list has at least one true value', () => {
        let { errors } = noneFalse(boolArrayWithTrue)({data: false, errors: []})
        expect(errors).toHaveLength(0);
    })

    it('raises no error if input list has only false values, but data is true', () => {
        let { errors } = noneFalse(boolArrayWithoutTrue)({data: true, errors: []})
        expect(errors).toHaveLength(0);
    })

    it('raises an error if input list has only false values, and data is false', () => {
        let { errors } = noneFalse(boolArrayWithoutTrue)({data: false, errors: []})
        expect(errors).toHaveLength(1);
    })
})

describe('validJobName', () => {
    it('raises no error if name contains only valid characters', () => {
        let { errors } = validJobName({data: allowedName, errors: []})
        expect(errors).toHaveLength(0);
    })

    it('raises an error if name contains at least one invalid character', () => {
        let { errors } = validJobName({data: disallowedName, errors: []})
        expect(errors).toHaveLength(1);
    })
})

describe('checkForErrors', () => {
    it('creates an array with multiple error messages from each error test', () => {
        const errors = checkForErrors(shorterThan(5), notEmpty, isNumber, validJobName)(disallowedName)
        expect(errors).toHaveLength(3); // Should check all of the above errors except for notEmpty
    })
})
