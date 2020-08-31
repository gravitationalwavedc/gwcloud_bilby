// Set the harnessApi
import React from "react";
import { MockPayloadGenerator } from "relay-test-utils";

import { graphql } from "react-relay";
import { expect } from "@jest/globals";
import { within, render, cleanup, screen, fireEvent, getRoles } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import JobParameters from "../JobParameters";

const testData = {
    dataChoice: 'open',
    hanford: true,
    livingston: false,
    virgo: true,
    signalDuration: '4',
    samplingFrequency: '16384',
    triggerTime: '2.1',
    hanfordMinimumFrequency: '20',
    hanfordMaximumFrequency: '1024',
    hanfordChannel: 'GWOSC',
    livingstonMinimumFrequency: '20',
    livingstonMaximumFrequency: '1024',
    livingstonChannel: 'GWOSC',
    virgoMinimumFrequency: '20',
    virgoMaximumFrequency: '1024',
    virgoChannel: 'GWOSC'
}

const testSignal = {
    signalChoice: 'binaryBlackHole',
    signalModel: 'binaryBlackHole',
    mass1: '30',
    mass2: '25',
    luminosityDistance: '2000',
    psi: '0.4',
    iota: '2.659',
    phase: '1.3',
    mergerTime: '1126259642.413',
    ra: '1.375',
    dec: '-1.2108'
}

const testPrior = {
    priorChoice: '8s'
}

const testSampler = {
    samplerChoice: 'dynesty',
    nlive: '1000',
    nact: '10',
    maxmcmc: '5000',
    walks: '1000',
    dlogz: '0.1',
    cpus: '1'
}

const inputQuery = graphql`
    query JobParametersTestQuery @relay_test_operation {
        bilbyJob (id: 1) {
            ...JobParameters_bilbyJobParameters
        }
    }
`

function setup(inputState) {
    const environment = global.queryRendererSetup(
        inputQuery,
        (props) => <JobParameters bilbyJobParameters={props.bilbyJob}/>
    )

    environment.mock.resolveMostRecentOperation(operation =>
        MockPayloadGenerator.generate(operation, {
            DataType() {
                return testData
            },
            SignalType() {
                return testSignal
            },
            PriorType() {
                return testPrior
            },
            SamplerType() {
                return testSampler
            }
        }),
    );

    const detectorTable = screen.getByTestId('detectorTable')
    const dataTable = screen.getByTestId('dataTable')
    const signalTable = screen.getByTestId('signalTable')
    const samplerTable = screen.getByTestId('samplerTable')

    return {
        detectorRows: {
            hanford: within(detectorTable).queryByRole('row', {name: /hanford/i}),
            livingston: within(detectorTable).queryByRole('row', {name: /livingston/i}),
            virgo: within(detectorTable).queryByRole('row', {name: /virgo/i}),
        },

        dataRows: {
            signalDuration: within(dataTable).queryByRole('row', {name: /signal duration/i}),
            samplingFrequency: within(dataTable).queryByRole('row', {name: /sampling frequency/i}),
            triggerTime: within(dataTable).queryByRole('row', {name: /trigger time/i}),
        },

        signalRows: {
            signalChoice: within(signalTable).queryByRole('row', {name: /injected signal/i}),
            mass1: within(signalTable).queryByRole('row', {name: /mass 1/i}),
            mass2: within(signalTable).queryByRole('row', {name: /mass 2/i}),
            luminosityDistance: within(signalTable).queryByRole('row', {name: /luminosity distance/i}),
            psi: within(signalTable).queryByRole('row', {name: /psi/i}),
            iota: within(signalTable).queryByRole('row', {name: /iota/i}),
            phase: within(signalTable).queryByRole('row', {name: /phase/i}),
            mergerTime: within(signalTable).queryByRole('row', {name: /merger time/i}),
            ra: within(signalTable).queryByRole('row', {name: /right ascension/i}),
            dec: within(signalTable).queryByRole('row', {name: /declination/i})
        },

        samplerRows: {
            nlive: within(samplerTable).queryByRole('row', {name: /number of live points/i}),
            nact: within(samplerTable).queryByRole('row', {name: /number of auto-correlation steps/i}),
            maxmcmc: within(samplerTable).queryByRole('row', {name: /maximum number of steps/i}),
            walks: within(samplerTable).queryByRole('row', {name: /minimum number of walks/i}),
            dlogz: within(samplerTable).queryByRole('row', {name: /stopping criteria/i}),
        }
    }
}

describe('Detector table displays the detector parameters if they are being used:', () => {
    let fields
    beforeAll(() => {fields = setup()})
    afterAll(cleanup)

    it('hanford is displayed correctly', () => {
        expect(fields.detectorRows.hanford).toBeInTheDocument()
        expect(within(fields.detectorRows.hanford).getByText(testData.hanfordChannel)).toBeInTheDocument()
        expect(within(fields.detectorRows.hanford).getByText(testData.hanfordMinimumFrequency)).toBeInTheDocument()
        expect(within(fields.detectorRows.hanford).getByText(testData.hanfordMaximumFrequency)).toBeInTheDocument()
    })

    it('livingston was not used, hence it is hidden', () => {
        expect(fields.detectorRows.livingston).not.toBeInTheDocument()
    })

    it('virgo is displayed correctly', () => {
        expect(fields.detectorRows.virgo).toBeInTheDocument()
        expect(within(fields.detectorRows.virgo).getByText(testData.virgoChannel)).toBeInTheDocument()
        expect(within(fields.detectorRows.virgo).getByText(testData.virgoMinimumFrequency)).toBeInTheDocument()
        expect(within(fields.detectorRows.virgo).getByText(testData.virgoMaximumFrequency)).toBeInTheDocument()
    })
})

describe('Data table displays the correct data parameters:', () => {
    let fields
    beforeAll(() => {fields = setup()})
    afterAll(cleanup)

    it('signalDuration is displayed correctly', () => {
        expect(fields.dataRows.signalDuration).toBeInTheDocument()
        expect(within(fields.dataRows.signalDuration).getByText(testData.signalDuration)).toBeInTheDocument()
    })

    it('samplingFrequency is displayed correctly', () => {
        expect(fields.dataRows.samplingFrequency).toBeInTheDocument()
        expect(within(fields.dataRows.samplingFrequency).getByText(testData.samplingFrequency)).toBeInTheDocument()
    })

    it('triggerTime is displayed correctly', () => {
        expect(fields.dataRows.triggerTime).toBeInTheDocument()
        expect(within(fields.dataRows.triggerTime).getByText(testData.triggerTime)).toBeInTheDocument()
    })
})

describe('Signal table displays the correct signal parameters:', () => {
    let fields
    beforeAll(() => {fields = setup()})
    afterAll(cleanup)

    it('signalChoice is displayed correctly', () => {
        expect(fields.signalRows.signalChoice).toBeInTheDocument()
        expect(within(fields.signalRows.signalChoice).getByText('Binary Black Hole')).toBeInTheDocument()
    })

    it('mass1 is displayed correctly', () => {
        expect(fields.signalRows.mass1).toBeInTheDocument()
        expect(within(fields.signalRows.mass1).getByText(testSignal.mass1)).toBeInTheDocument()
    })

    it('mass2 is displayed correctly', () => {
        expect(fields.signalRows.mass2).toBeInTheDocument()
        expect(within(fields.signalRows.mass2).getByText(testSignal.mass2)).toBeInTheDocument()
    })

    it('luminosityDistance is displayed correctly', () => {
        expect(fields.signalRows.luminosityDistance).toBeInTheDocument()
        expect(within(fields.signalRows.luminosityDistance).getByText(testSignal.luminosityDistance)).toBeInTheDocument()
    })

    it('psi is displayed correctly', () => {
        expect(fields.signalRows.psi).toBeInTheDocument()
        expect(within(fields.signalRows.psi).getByText(testSignal.psi)).toBeInTheDocument()
    })

    it('iota is displayed correctly', () => {
        expect(fields.signalRows.iota).toBeInTheDocument()
        expect(within(fields.signalRows.iota).getByText(testSignal.iota)).toBeInTheDocument()
    })

    it('phase is displayed correctly', () => {
        expect(fields.signalRows.phase).toBeInTheDocument()
        expect(within(fields.signalRows.phase).getByText(testSignal.phase)).toBeInTheDocument()
    })

    it('mergerTime is displayed correctly', () => {
        expect(fields.signalRows.mergerTime).toBeInTheDocument()
        expect(within(fields.signalRows.mergerTime).getByText(testSignal.mergerTime)).toBeInTheDocument()
    })

    it('ra is displayed correctly', () => {
        expect(fields.signalRows.ra).toBeInTheDocument()
        expect(within(fields.signalRows.ra).getByText(testSignal.ra)).toBeInTheDocument()
    })

    it('dec is displayed correctly', () => {
        expect(fields.signalRows.dec).toBeInTheDocument()
        expect(within(fields.signalRows.dec).getByText(testSignal.dec)).toBeInTheDocument()
    })
})

describe('Sampler table displays the correct sampler parameters:', () => {
    let fields
    beforeAll(() => {fields = setup()})
    afterAll(cleanup)

    it('nlive is displayed correctly', () => {
        expect(fields.samplerRows.nlive).toBeInTheDocument()
        expect(within(fields.samplerRows.nlive).getByText(testSampler.nlive)).toBeInTheDocument()
    })

    it('nact is displayed correctly', () => {
        expect(fields.samplerRows.nact).toBeInTheDocument()
        expect(within(fields.samplerRows.nact).getByText(testSampler.nact)).toBeInTheDocument()
    })

    it('maxmcmc is displayed correctly', () => {
        expect(fields.samplerRows.maxmcmc).toBeInTheDocument()
        expect(within(fields.samplerRows.maxmcmc).getByText(testSampler.maxmcmc)).toBeInTheDocument()
    })

    it('walks is displayed correctly', () => {
        expect(fields.samplerRows.walks).toBeInTheDocument()
        expect(within(fields.samplerRows.walks).getByText(testSampler.walks)).toBeInTheDocument()
    })

    it('dlogz is displayed correctly', () => {
        expect(fields.samplerRows.dlogz).toBeInTheDocument()
        expect(within(fields.samplerRows.dlogz).getByText(testSampler.dlogz)).toBeInTheDocument()
    })
})