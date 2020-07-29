// Set the harnessApi
import React from "react";
import { MockPayloadGenerator } from "relay-test-utils";

import { graphql } from "react-relay";
import { expect } from "@jest/globals";
import { within, cleanup, screen, fireEvent, logRoles } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import JobLabelDropdown from "../JobLabelDropdown";

const testData = {
    labels: [
        {name: 'Test Label 1'}
    ]
}

const testLabels = {allLabels: [
    {name: 'Test Label 1', description: 'A test label'},
    {name: 'Test Label 2', description: 'Another test label'},
]}

const inputQuery = graphql`
    query JobLabelDropdownTestQuery @relay_test_operation {
        ...JobLabelDropdown_data @arguments(jobId: 1)
    }
`

function setup() {
    const environment = global.queryRendererSetup(
        inputQuery,
        (props) => <JobLabelDropdown jobId={1} data={props}/>
    )

    environment.mock.resolveMostRecentOperation(operation =>
        MockPayloadGenerator.generate(operation, {
            BilbyJobNode() {
                return testData
            },
            Query() {
                return testLabels
            }
        }),
    );
    const dropdown = screen.getByRole('listbox')
    const label1 = within(dropdown).getByText('Test Label 1')
    const label2 = within(dropdown).getByText('Test Label 2')

    const option1 = within(dropdown).queryByRole('option', {name: /test label 1/i})
    const option2 = within(dropdown).queryByRole('option', {name: /test label 2/i})

    return {
        dropdown: dropdown,
        label1: label1,
        label2: label2,
        option1: option1,
        option2: option2
    }
}

// These tests are kind of garbage
describe('Label dropdown', () => {
    let fields
    beforeAll(() => {fields = setup()})
    afterAll(cleanup)

    it('displays the initial state correctly', () => {
        expect(fields.dropdown).toBeInTheDocument()
        expect(fields.label1).toBeInTheDocument()

        // Test Label 1 will not exist as an option, because it has been selected
        expect(fields.option1).not.toBeInTheDocument()
        expect(fields.option2).toBeInTheDocument()
    })

    it('allows labels to be selected', () => {
        fireEvent.click(fields.option2)
        expect(fields.option2).not.toBeInTheDocument()
    })
})