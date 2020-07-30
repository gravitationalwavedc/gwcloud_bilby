import {expect} from "@jest/globals";
import { unCamelCase, mergeUnlessNull, formatDate } from "../utilMethods";

// Just testing all the error functions

describe('unCamelCase', () => {
    const camelCase = 'sentenceToTestSpreadingOfCamelCase'
    const expected = 'Sentence To Test Spreading Of Camel Case'

    it('changes a string in camelCase to be formatted with spaces and the first letter capitalised', () => {
        const unCamelCased = unCamelCase(camelCase)
        expect(unCamelCased).toEqual(expected);
    })
})

describe('mergeUnlessNull', () => {
    it('can merge two objects', () => {
        const obj1 = {
            a: 1,
            b: '2',
            c: [1,2,3],
        }
    
        const obj2 = {
            a: 10,
            b: '20',
            d: {test: 'test'}
        }

        const merged = mergeUnlessNull({}, obj1, obj2)
        expect(merged).toEqual({...obj1, ...obj2});
    })
    
    it('can merge three objects', () => {
        const obj1 = {
            a: 1,
            b: '2',
            c: [1,2,3],
        }
    
        const obj2 = {
            a: 10,
            b: '20',
            d: {test: 'test'}
        }

        const obj3 = {
            a: 10,
            b: '20',
            e: 10.0
        }

        const merged = mergeUnlessNull(obj1, obj2, obj3)
        expect(merged).toEqual({...obj1, ...obj2, ...obj3});
    })

    it('nulls don\'t overwrite values', () => {
        const expected = {
            a: 1,
            b: '2',
            c: [1,2,3],
        }
    
        const obj1 = {
            a: null,
            b: '2',
            c: [1,2,3]
        }
        
        const obj2 = {
            a: 1,
            b: null,
            c: [1,2,3]
        }
        
        const obj3 = {
            a: null,
            b: null,
            c: null
        }
        
        const merged = mergeUnlessNull(obj1, obj2, obj3)
        expect(merged).toEqual(expected);
    })

    it('null object doesn\'t overwrite values', () => {
        const expected = {
            a: 1,
            b: '2',
            c: [1,2,3],
        }
    
        const obj1 = {
            a: null,
            b: '2',
            c: [1,2,3]
        }
        
        const obj2 = {
            a: 1,
            b: null,
            c: [1,2,3]
        }
        
        const obj3 = null

        const merged = mergeUnlessNull(obj1, obj2, obj3)
        expect(merged).toEqual(expected);
    })
})

describe('formatDate', () => {
    const UTCDate = "2020-06-15 12:30:30 UTC"
    const AESTDate = "6/15/2020, 22:30:30"
    it('correctly changes the date format from UTC to the date of the current timezone', () => {
        expect(formatDate(UTCDate, "en-AU")).toBe(AESTDate)
    })
})
