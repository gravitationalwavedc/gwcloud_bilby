// Set the harnessApi
import React from "react";
import { MockPayloadGenerator } from "relay-test-utils";

import { graphql } from "react-relay";
import { expect } from "@jest/globals";
import { within, render, cleanup, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import SamplerForm from "../SamplerForm";

const testEmptyFunction = () => {}

const testData = {
    samplerChoice: 'dynesty',
    nlive: '1000',
    nact: '10',
    maxmcmc: '5000',
    walks: '1000',
    dlogz: '0.1',
    cpus: '1'
}

const inputQuery = graphql`
    query SamplerFormTestQuery @relay_test_operation {
        bilbyJob (id: 1) {
            sampler {
            ...SamplerForm_data
            }
        }
    }
`
function setup(inputState) {
    const environment = global.queryRendererSetup(
        inputQuery,
        (props) => <SamplerForm data={props.bilbyJob.sampler} state={inputState} updateParentState={testEmptyFunction} nextStep={testEmptyFunction}/>
    )

    environment.mock.resolveMostRecentOperation(operation =>
        MockPayloadGenerator.generate(operation, {
            SamplerType() {
                return testData
            }
        }),
    );

    return {
        samplerChoice: screen.getByLabelText('Sampler'),
        nlive: screen.getByLabelText('Number of live points'),
        nact: screen.getByLabelText('Number of auto-correlation steps'),
        maxmcmc: screen.getByLabelText('Maximum number of steps'),
        walks: screen.getByLabelText('Minimum number of walks'),
        dlogz: screen.getByLabelText('Stopping criteria'),
        cpus: screen.getByLabelText('Number of CPUs to use for parallelisation')
    }
}

describe('Sampler form displays the initial form fields and values correctly:', () => {
    let fields
    beforeAll(() => {fields = setup({sameSignal: false})})
    afterAll(cleanup)

    it('samplerChoice', () => {
        expect(fields.samplerChoice).toBeInTheDocument()
        expect(within(fields.samplerChoice).getByRole('alert')).toHaveTextContent('Dynesty')
    })

    it('nlive', () => {
        expect(fields.nlive).toBeInTheDocument()
        expect(fields.nlive).toHaveValue(testData.nlive)
    })

    it('nact', () => {
        expect(fields.nact).toBeInTheDocument()
        expect(fields.nact).toHaveValue(testData.nact)
    })

    it('maxmcmc', () => {
        expect(fields.maxmcmc).toBeInTheDocument()
        expect(fields.maxmcmc).toHaveValue(testData.maxmcmc)
    })

    it('walks', () => {
        expect(fields.walks).toBeInTheDocument()
        expect(fields.walks).toHaveValue(testData.walks)
    })

    it('dlogz', () => {
        expect(fields.dlogz).toBeInTheDocument()
        expect(fields.dlogz).toHaveValue(testData.dlogz)
    })

    it('cpus', () => {
        expect(fields.cpus).toBeInTheDocument()
        expect(fields.cpus).toHaveValue(testData.cpus)
    })
})