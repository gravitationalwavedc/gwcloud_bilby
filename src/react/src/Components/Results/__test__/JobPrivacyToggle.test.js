// Set the harnessApi
import React from "react";
import { MockPayloadGenerator } from "relay-test-utils";

import { graphql } from "react-relay";
import { expect } from "@jest/globals";
import { cleanup, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import JobPrivacyToggle from "../JobPrivacyToggle";

const testData = {
    private: false
}

const inputQuery = graphql`
    query JobPrivacyToggleTestQuery @relay_test_operation {
        bilbyJob (id: 1) {
            start {
                ...JobPrivacyToggle_data
            }
        }
    }
`

function setup() {
    const environment = global.queryRendererSetup(
        inputQuery,
        (props) => <JobPrivacyToggle userId={1} jobId={1} data={props.bilbyJob.start}/>
    )

    environment.mock.resolveMostRecentOperation(operation =>
        MockPayloadGenerator.generate(operation, {
            OutputStartType() {
                return testData
            }
        }),
    );

    return {
        toggle: screen.getByRole('checkbox')
    }
}

describe('Privacy toggle', () => {
    let fields
    beforeAll(() => {fields = setup()})
    afterAll(cleanup)

    it('displays the initial state correctly', () => {
        expect(fields.toggle).toBeInTheDocument()
        expect(fields.toggle).not.toBeChecked()
    })

    it('handles being clicked correctly', () => {
        fireEvent.click(fields.toggle)
        expect(fields.toggle).toBeChecked()
    })
})