// Set the harnessApi
import React from "react";
import { MockPayloadGenerator } from "relay-test-utils";

import { graphql } from "react-relay";
import { expect } from "@jest/globals";
import { within, render, cleanup, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import SignalForm from "../SignalForm";

const testEmptyFunction = () => {}

const testData = {
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

const inputQuery = graphql`
    query SignalFormTestQuery @relay_test_operation {
        bilbyJob (id: 1) {
            signal {
            ...SignalForm_data
            }
        }
    }
`
function setup(inputState) {
    const environment = global.queryRendererSetup(
        inputQuery,
        (props) => <SignalForm data={props.bilbyJob.signal} state={inputState} updateParentState={testEmptyFunction} nextStep={testEmptyFunction} openData={true}/>
    )

    environment.mock.resolveMostRecentOperation(operation =>
        MockPayloadGenerator.generate(operation, {
            SignalType() {
                return testData
            }
        }),
    );

    return {
        signalChoice: screen.getByLabelText('Signal Inject'),
        signalModel: screen.getByLabelText('Signal Model'),
        mass1: screen.getByLabelText(/mass 1/i),
        mass2: screen.getByLabelText(/mass 2/i),
        luminosityDistance: screen.getByLabelText(/luminosity distance/i),
        psi: screen.getByLabelText('psi'),
        iota: screen.getByLabelText('iota'),
        phase: screen.getByLabelText('Phase'),
        mergerTime: screen.getByLabelText(/merger time/i),
        ra: screen.getByLabelText(/right ascension/i),
        dec: screen.getByLabelText(/declination/i),
        sameSignal: screen.getByLabelText('Same Signal for Model')
    }
}

describe('Signal form displays the initial form fields and values correctly:', () => {
    let fields
    beforeAll(() => {fields = setup({sameSignal: false})})
    afterAll(cleanup)

    it('signalChoice', () => {
        expect(fields.signalChoice).toBeInTheDocument()
        expect(within(fields.signalChoice).getByRole('alert')).toHaveTextContent('Binary Black Hole')
    })

    it('mass1', () => {
        expect(fields.mass1).toBeInTheDocument()
        expect(fields.mass1).toHaveValue(testData.mass1)
    })

    it('mass2', () => {
        expect(fields.mass2).toBeInTheDocument()
        expect(fields.mass2).toHaveValue(testData.mass2)
    })

    it('luminosityDistance', () => {
        expect(fields.luminosityDistance).toBeInTheDocument()
        expect(fields.luminosityDistance).toHaveValue(testData.luminosityDistance)
    })

    it('psi', () => {
        expect(fields.psi).toBeInTheDocument()
        expect(fields.psi).toHaveValue(testData.psi)
    })

    it('iota', () => {
        expect(fields.iota).toBeInTheDocument()
        expect(fields.iota).toHaveValue(testData.iota)
    })

    it('phase', () => {
        expect(fields.phase).toBeInTheDocument()
        expect(fields.phase).toHaveValue(testData.phase)
    })

    it('mergerTime', () => {
        expect(fields.mergerTime).toBeInTheDocument()
        expect(fields.mergerTime).toHaveValue(testData.mergerTime)
    })

    it('ra', () => {
        expect(fields.ra).toBeInTheDocument()
        expect(fields.ra).toHaveValue(testData.ra)
    })

    it('dec', () => {
        expect(fields.dec).toBeInTheDocument()
        expect(fields.dec).toHaveValue(testData.dec)
    })

    it('sameSignal', () => {
        expect(fields.sameSignal).toBeInTheDocument()
        expect(fields.sameSignal).not.toBeChecked()
    })

    it('signalModel', () => {
        expect(fields.signalModel).toBeInTheDocument()
        expect(within(fields.signalModel).getByRole('alert')).toHaveTextContent('Binary Black Hole')
    })
})

describe('Signal form dynamically', () => {
    let fields
    beforeAll(() => {fields = setup({sameSignal: false})})
    afterAll(cleanup)

    it('hides signalModel field when sameSignal checkbox is checked', () => {
        expect(fields.sameSignal).toBeInTheDocument()
        expect(fields.signalModel).toBeInTheDocument()

        fireEvent.click(fields.sameSignal)
        expect(fields.sameSignal).toBeChecked()

        expect(fields.signalModel).not.toBeInTheDocument()
    })
})