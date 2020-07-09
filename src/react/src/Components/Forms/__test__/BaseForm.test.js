// Set the harnessApi
import React from "react";
import { expect } from "@jest/globals";
import { fireEvent, render, cleanup, screen } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import { Form } from "semantic-ui-react";
import BaseForm from "../BaseForm";

const testFormLabel = 'Test Form'
const testFormValue = 'testValue'
const testFormName = 'test'

const testEmptyFunction = () => { }


describe('BaseForm', () => {
    afterEach(cleanup)

    function setup() {
        const prevStep = jest.fn(testEmptyFunction)
        const nextStep = jest.fn(testEmptyFunction)
        render (
            <BaseForm
                initialData={{
                    [testFormName]: testFormValue,
                }}
                setForms={(values) => {
                    return [
                        {
                            label: testFormLabel,
                            name: testFormName,
                            form: <Form.Input />,
                        },
                    ]
                }}
                prevStep={prevStep}
                nextStep={nextStep}
                updateParentState={testEmptyFunction}
            />
        )
        const backButton = screen.getByText('Back')
        const nextButton = screen.getByText('Save and Continue')

        return {backButton, nextButton, prevStep, nextStep}
    }

    it('renders back and next buttons', () => {
        const {backButton, nextButton} = setup()
        expect(backButton).toBeInTheDocument()
        expect(nextButton).toBeInTheDocument()
    })

    it('assigns prevStep and nextStep to be called on click of the back and next buttons', () => {
        const {backButton, nextButton, prevStep, nextStep} = setup()

        expect(prevStep).not.toHaveBeenCalled()
        fireEvent.click(backButton)
        expect(prevStep).toHaveBeenCalled()

        expect(nextStep).not.toHaveBeenCalled()
        fireEvent.click(nextButton)
        expect(nextStep).toHaveBeenCalled()
    })

})


