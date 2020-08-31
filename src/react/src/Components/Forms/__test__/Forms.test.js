// Set the harnessApi
import React from "react";
import { expect } from "@jest/globals";
import { fireEvent, render, cleanup, screen } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import { Form, Grid } from "semantic-ui-react";
import { createValidationFunction, assembleErrorString, isShorterThan, isLongerThan, checkForErrors } from "../../../Utils/errors";
import { FormController, InputField } from "../Forms";

const testFormLabel = 'Test Form'
const testFormValue = 'testValue'
const testFormName = 'test'

const testFormLabel2 = 'Test Form 2'
const testFormValue2 = 'testValue2'
const testFormName2 = 'test2'

const testFormValue3 = 'testValue3'
const testFormValue4 = 'testValue4'

const testEmptyFunction = () => { }

function contextRender(setForms) {
    const props = {
        initialValues: {
            [testFormName]: testFormValue,
            [testFormName2]: testFormValue2,
        },
        onSubmit: testEmptyFunction,
        validate: (values) => createValidationFunction(
            {
                [testFormName]: [isShorterThan(5)],
                [testFormName2]: [isLongerThan(15)],
            },
            values
        ),
        linkedErrors: {
            [testFormName]: [testFormName2]
        },
        linkedValues: (fieldName, fieldValue, values) => {
            switch (fieldName) {
                case testFormName:
                    if (fieldValue === testFormValue3) {
                        return {[testFormName2]: testFormValue4}
                    }
                    break;
                default:
                    break;
            }
    
        }
    }
    render(
        <FormController {...props}>
            {({values}) => setForms(values)}
        </FormController>
    )
}

describe('FormController rendering some InputFields ', () => {
    afterEach(cleanup)

    function setup() {
        function setForms(values) {
            return (
                <React.Fragment>
                    <InputField name={testFormName} label={testFormLabel} />
                    {values[testFormName] === testFormValue2 ? null : <InputField name={testFormName2} label={testFormLabel2} />}
                </React.Fragment>
            )
        }
        contextRender(setForms)
        const inputField = screen.getByLabelText(testFormLabel)
        const inputField2 = screen.queryByLabelText(testFormLabel2)
        return {inputField, inputField2}
    }

    it('places initial values in the correct InputFields', () => {
        const {inputField, inputField2} = setup()
        expect(inputField).toHaveValue(testFormValue)
        expect(inputField2).toHaveValue(testFormValue2)
    })

    it('modifies value if the conditions in linkedValues are met', () => {
        const {inputField, inputField2} = setup()
        expect(inputField2).toHaveValue(testFormValue2)
        fireEvent.change(inputField, {target: {value: testFormValue3}})
        expect(inputField2).toHaveValue(testFormValue4)
    })

    it('shows an error message if the InputField value is not valid on blur', () => {
        const {inputField} = setup()
        const errors = checkForErrors(isShorterThan(5))(testFormValue)
        expect(screen.queryByText(assembleErrorString(errors))).not.toBeInTheDocument()
        fireEvent.focus(inputField)
        fireEvent.blur(inputField)
        expect(screen.getByText(assembleErrorString(errors))).toBeInTheDocument()
    })

    it('shows an error message if the InputField value is not valid on blur of linked field', () => {
        const {inputField} = setup()
        const errors = checkForErrors(isLongerThan(15))(testFormValue2)
        expect(screen.queryByText(assembleErrorString(errors))).not.toBeInTheDocument()
        fireEvent.focus(inputField)
        fireEvent.blur(inputField)
        expect(screen.getByText(assembleErrorString(errors))).toBeInTheDocument()
    })

    it('handles hiding fields in setForms', () => {
        const {inputField, inputField2} = setup()
        expect(inputField2).toBeInTheDocument()
        fireEvent.change(inputField, {target: {value: testFormValue2}})
        expect(inputField2).not.toBeInTheDocument()
    })

})