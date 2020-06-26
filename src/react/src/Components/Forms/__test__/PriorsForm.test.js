// Set the harnessApi
import React from "react";
import { MockPayloadGenerator } from "relay-test-utils";
import { QueryRenderer } from 'react-relay';

import { graphql } from "react-relay";
import { expect } from "@jest/globals";
import { within, render, cleanup, screen } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import PriorsForm from "../PriorsForm";

const testEmptyFunction = () => {}
const priorChoiceQueryValue = '8s'

const inputQuery = graphql`
    query PriorsFormTestQuery @relay_test_operation {
        bilbyJob (id: 1) {
            prior {
            ...PriorsForm_data
            }
        }
    }
`
function setup(inputState) {
    const environment = global.queryRendererSetup(
        inputQuery,
        (props) => <PriorsForm data={props.bilbyJob.prior} state={inputState} updateParentState={testEmptyFunction} prevStep={testEmptyFunction} nextStep={testEmptyFunction} />
    )

    environment.mock.resolveMostRecentOperation(operation =>
        MockPayloadGenerator.generate(operation, {
            PriorType() {
                return {
                    priorChoice: priorChoiceQueryValue,
                }
            }
        }),
    );

    const priorChoiceField = screen.getByLabelText('Default Prior')
    const priorChoiceDisplay = within(priorChoiceField).getByRole('alert')

    return { priorChoiceField, priorChoiceDisplay }
}

describe('Priors Form', () => {
    afterEach(cleanup)

    it('checks that the priorChoice form is showing the correct value', () => {
        const { priorChoiceField, priorChoiceDisplay } = setup(null)

        expect(priorChoiceField).toBeInTheDocument()
        expect(priorChoiceDisplay).toHaveTextContent(priorChoiceQueryValue)
    })
})