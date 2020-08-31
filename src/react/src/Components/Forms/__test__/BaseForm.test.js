// Set the harnessApi
import React from "react";
import { expect } from "@jest/globals";
import { fireEvent, render, cleanup, screen } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import BaseForm from "../BaseForm";
import { InputField } from "../Forms";
import { StepController } from "../../Utils/Steps";

const testFormLabel = 'Test Form'
const testFormValue = 'testValue'
const testFormName = 'test'

const testEmptyFunction = () => { }


describe('BaseForm', () => {
    afterEach(cleanup)

    function setup(initialStep) {
        const onSubmit = jest.fn(testEmptyFunction)

        const steps = [
            {name: 'Step 1', description: 'Step 1'},
            {name: 'Step 2', description: 'Step 2'}
        ]

        render (
            <StepController 
                steps={steps}
                initialStep={initialStep} >
                    {
                        (step) => (
                            <BaseForm
                                formProps={{
                                    initialValues: {[testFormName]: testFormValue},
                                    onSubmit: onSubmit,
                                }}
                                setForms={(values) => {
                                    <InputField label={testFormLabel} name={testFormName} />
                                }}
                            />
                        )
                    }
                </StepController>

        )
        const backButton = screen.queryByText('Save and Back')
        const nextButton = screen.queryByText('Save and Continue')

        return {backButton, nextButton, onSubmit}
    }

    it('binds onSubmit to next button', () => {
        const {nextButton, onSubmit} = setup(1)
        expect(nextButton).toBeInTheDocument()

        expect(onSubmit).not.toHaveBeenCalled()
        fireEvent.click(nextButton)
        expect(onSubmit).toHaveBeenCalled()
    })

    it('binds onSubmit to back button', () => {
        const {backButton, onSubmit} = setup(2)
        expect(backButton).toBeInTheDocument()

        expect(onSubmit).not.toHaveBeenCalled()
        fireEvent.click(backButton)
        expect(onSubmit).toHaveBeenCalled()
    })


})


