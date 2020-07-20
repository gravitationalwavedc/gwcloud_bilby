// Set the harnessApi
import React from "react";
import { MockPayloadGenerator } from "relay-test-utils";

import { graphql } from "react-relay";
import { expect } from "@jest/globals";
import { within, render, cleanup, screen } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import StartForm from "../StartForm";

const testEmptyFunction = () => {}
const nameQueryValue = 'TestJob'
const descriptionQueryValue = 'Test description'
const privateQueryValue = true

const inputQuery = graphql`
    query StartFormTestQuery @relay_test_operation {
        bilbyJob (id: 1) {
            start {
            ...StartForm_data
            }
        }
    }
`
function setup(inputState) {
    const environment = global.queryRendererSetup(
        inputQuery,
        (props) => <StartForm data={props.bilbyJob.start} state={inputState} updateParentState={testEmptyFunction} nextStep={testEmptyFunction} />
    )

    environment.mock.resolveMostRecentOperation(operation =>
        MockPayloadGenerator.generate(operation, {
            OutputStartType() {
                return {
                    name: nameQueryValue,
                    description: descriptionQueryValue,
                    private: privateQueryValue,
                }
            }
        }),
    );

    const nameField = screen.getByLabelText('Job Name')
    const descriptionField = screen.getByLabelText('Job Description')
    const privateField = screen.getByLabelText('Private Job')

    return { nameField, descriptionField, privateField }
}

describe('Start Form', () => {
    afterEach(cleanup)

    it('displays the initial form fields and values correctly', () => {
        const { nameField, descriptionField, privateField } = setup(null)

        expect(nameField).toBeInTheDocument()
        expect(nameField).toHaveValue(nameQueryValue)

        expect(descriptionField).toBeInTheDocument()
        expect(descriptionField).toHaveValue(descriptionQueryValue)

        expect(privateField).toBeInTheDocument()
        expect(privateField).toBeChecked()
    })
})