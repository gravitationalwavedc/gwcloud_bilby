// Set the harnessApi
import React from "react";
import { expect } from "@jest/globals";
import { fireEvent, render, cleanup, screen } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import { FormController, FormField } from "../Forms";
import { Form, Grid } from "semantic-ui-react";
import { checkForErrors, assembleErrorString, isShorterThan } from "../../../Utils/errors";

const testFormLabel = 'Test Form'
const testFormValue = 'testValue'
const testFormName = 'test'

const testFormLabel2 = 'Test Form 2'
const testFormValue2 = 'testValue2'
const testFormName2 = 'test2'

const testEmptyFunction = () => { }


describe('FormField', () => {

    afterEach(cleanup)

    let props = {
        values: { [testFormName]: testFormValue },
        errors: { [testFormName]: [] },
        validating: false,
        handleChange: testEmptyFunction,
        handleVisibility: testEmptyFunction,
        setValid: testEmptyFunction,
        setInitial: testEmptyFunction
    }


    it('places initial value in the form field', () => {
        render(<FormField name={testFormName} label={testFormLabel} form={<Form.Input />} {...props} />)
        expect(screen.getByLabelText(testFormLabel)).toHaveValue(testFormValue)
    })

    it('shows an error message if validating', () => {
        const errors = checkForErrors(isShorterThan(5))(testFormValue)
        props.validating = true
        props.errors = { [testFormName]: errors }

        render(<FormField name={testFormName} label={testFormLabel} form={<Form.Input />} {...props} />)
        expect(screen.getByText(assembleErrorString(errors))).toBeInTheDocument()
    })

    it('is hidden if visible is set to false', () => {
        render(<FormField name={testFormName} label={testFormLabel} form={<Form.Input />} visible={false} {...props} />)
        expect(screen.queryByLabelText(testFormLabel)).not.toBeInTheDocument()
    })

})

describe('Form Controller with Form Field', () => {
    afterEach(cleanup)

    function setup(validating) {
        render (
            <FormController
                initialValues={{ 
                    [testFormName]: testFormValue,
                    [testFormName2]: testFormValue2,
                }}
                validating={validating}
                onValid={() => {}}
            >
                {
                    props => {
                        return (
                            <Form>
                                <Grid textAlign='left'>
                                    <FormField name={testFormName} label={testFormLabel} form={<Form.Input />} errFunc={checkForErrors(isShorterThan(5))} visible={props.values[testFormName2] !== 'Invisible'} {...props} />
                                    <FormField name={testFormName2} label={testFormLabel2} form={<Form.Input />} valFunc={(val) => val === 'Update First Field' ? {[testFormName]: 'Updated'} : {}} {...props} />
                                </Grid>
                            </Form>
                        )
                    }
                }
            </FormController>
        )
        const testForm = screen.getByLabelText(testFormLabel)
        const testForm2 = screen.getByLabelText(testFormLabel2)

        return {testForm, testForm2}
    }

    it('places initial values in the correct form fields', () => {
        const {testForm, testForm2} = setup(false)
        expect(testForm).toHaveValue(testFormValue)
        expect(testForm2).toHaveValue(testFormValue2)
    })
    
    it('changes form field values dynamically when the conditions are met', () => {
        const {testForm, testForm2} = setup(false)
        
        expect(testForm).toHaveValue(testFormValue)
        fireEvent.change(testForm2, {target: {value: 'Update First Field'}})
        expect(testForm).toHaveValue('Updated')
    })
    
    it('changes visibility dynamically when the conditions are met', () => {
        const {testForm, testForm2} = setup(false)

        expect(testForm).toBeInTheDocument()
        fireEvent.change(testForm2, {target: {value: 'Invisible'}})
        expect(testForm).not.toBeInTheDocument()
    })

})

