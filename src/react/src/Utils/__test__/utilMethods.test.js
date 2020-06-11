import {expect} from "@jest/globals";
import { unCamelCase } from "../utilMethods";

// Just testing all the error functions

let camelCase = 'sentenceToTestSpreadingOfCamelCase'
let expected = 'Sentence To Test Spreading Of Camel Case'

describe('unCamelCase', () => {
    it('changes a string in camelCase to be formatted with spaces and the first letter capitalised', () => {
        const unCamelCased = unCamelCase(camelCase)
        expect(unCamelCased).toEqual(expected);
    })
})
