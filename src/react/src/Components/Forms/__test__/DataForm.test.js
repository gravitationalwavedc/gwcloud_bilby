// Set the harnessApi
import React from "react";
import { MockPayloadGenerator } from "relay-test-utils";

import { graphql } from "react-relay";
import { expect } from "@jest/globals";
import { within, render, cleanup, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import DataForm from "../DataForm";

const testEmptyFunction = () => {}

const testData = {
    dataChoice: 'open',
    hanford: false,
    livingston: false,
    virgo: false,
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

const inputQuery = graphql`
    query DataFormTestQuery @relay_test_operation {
        bilbyJob (id: 1) {
            ...DataForm_data
        }
    }
`
function setup(inputState) {
    const environment = global.queryRendererSetup(
        inputQuery,
        (props) => <DataForm data={props.bilbyJob} state={inputState} updateParentState={testEmptyFunction} />
    )

    environment.mock.resolveMostRecentOperation(operation =>
        MockPayloadGenerator.generate(operation, {
            BilbyJobNode() {
                return {
                    data: testData
                }
            }
        }),
    );

    return {
        dataChoice: screen.getByLabelText('Type of Data'),
        hanford: screen.getByLabelText('Hanford'),
        livingston: screen.getByLabelText('Livingston'),
        virgo: screen.getByLabelText('Virgo'),
        signalDuration: screen.getByLabelText(/signal duration/i),
        samplingFrequency: screen.getByLabelText(/sampling frequency/i),
        triggerTime: screen.getByLabelText(/trigger time/i)
    }
}

describe('Data form displays the initial form fields and values correctly:', () => {
    let fields
    beforeAll(() => {fields = setup(null)})
    afterAll(cleanup)

    it('dataChoice', () => {
        expect(fields.dataChoice).toBeInTheDocument()
        expect(within(fields.dataChoice).getByRole('alert')).toHaveTextContent('Open')
    })

    it('hanford', () => {
        expect(fields.hanford).toBeInTheDocument()
        expect(fields.hanford).not.toBeChecked()
    })
    
    it('livingston', () => {
        expect(fields.livingston).toBeInTheDocument()
        expect(fields.livingston).not.toBeChecked()
    })

    it('virgo', () => {
        expect(fields.virgo).toBeInTheDocument()
        expect(fields.virgo).not.toBeChecked()
    })

    it('signalDuration', () => {
        expect(fields.signalDuration).toBeInTheDocument()
        expect(within(fields.signalDuration).getByRole('alert')).toHaveTextContent(testData.signalDuration)
    })

    it('samplingFrequency', () => {
        expect(fields.samplingFrequency).toBeInTheDocument()
        expect(within(fields.samplingFrequency).getByRole('alert')).toHaveTextContent(testData.samplingFrequency)
    })

    it('triggerTime', () => {
        expect(fields.triggerTime).toBeInTheDocument()
        expect(fields.triggerTime).toHaveValue(testData.triggerTime)
    })
})

describe('Data form displays associated fields when detector checkboxes are checked', () => {
    let fields
    beforeAll(() => {fields = setup({start: {name: "testJob"}})})
    afterAll(cleanup)

    it('hanford', () => {
        expect(fields.hanford).toBeInTheDocument()
        fireEvent.click(fields.hanford)
        expect(fields.hanford).toBeChecked()

        const hanfordChannelField = screen.getByLabelText(/hanford channel/i)
        const hanfordMinimumFrequencyField = screen.getByLabelText(/hanford minimum frequency/i)
        const hanfordMaximumFrequencyField = screen.getByLabelText(/hanford maximum frequency/i)


        expect(hanfordChannelField).toBeInTheDocument()
        expect(within(hanfordChannelField).getByRole('alert')).toHaveTextContent(testData.hanfordChannel)
        
        expect(hanfordMinimumFrequencyField).toBeInTheDocument()
        expect(hanfordMinimumFrequencyField).toHaveValue(testData.hanfordMinimumFrequency)
        
        expect(hanfordMaximumFrequencyField).toBeInTheDocument()
        expect(hanfordMaximumFrequencyField).toHaveValue(testData.hanfordMaximumFrequency)
    })

    it('livingston', () => {
        expect(fields.livingston).toBeInTheDocument()
        fireEvent.click(fields.livingston)
        expect(fields.livingston).toBeChecked()

        const livingstonChannelField = screen.getByLabelText(/livingston channel/i)
        const livingstonMinimumFrequencyField = screen.getByLabelText(/livingston minimum frequency/i)
        const livingstonMaximumFrequencyField = screen.getByLabelText(/livingston maximum frequency/i)


        expect(livingstonChannelField).toBeInTheDocument()
        expect(within(livingstonChannelField).getByRole('alert')).toHaveTextContent(testData.livingstonChannel)
        
        expect(livingstonMinimumFrequencyField).toBeInTheDocument()
        expect(livingstonMinimumFrequencyField).toHaveValue(testData.livingstonMinimumFrequency)
        
        expect(livingstonMaximumFrequencyField).toBeInTheDocument()
        expect(livingstonMaximumFrequencyField).toHaveValue(testData.livingstonMaximumFrequency)
    })

    it('virgo', () => {
        expect(fields.virgo).toBeInTheDocument()
        fireEvent.click(fields.virgo)
        expect(fields.virgo).toBeChecked()

        const virgoChannelField = screen.getByLabelText(/virgo channel/i)
        const virgoMinimumFrequencyField = screen.getByLabelText(/virgo minimum frequency/i)
        const virgoMaximumFrequencyField = screen.getByLabelText(/virgo maximum frequency/i)


        expect(virgoChannelField).toBeInTheDocument()
        expect(within(virgoChannelField).getByRole('alert')).toHaveTextContent(testData.virgoChannel)
        
        expect(virgoMinimumFrequencyField).toBeInTheDocument()
        expect(virgoMinimumFrequencyField).toHaveValue(testData.virgoMinimumFrequency)
        
        expect(virgoMaximumFrequencyField).toBeInTheDocument()
        expect(virgoMaximumFrequencyField).toHaveValue(testData.virgoMaximumFrequency)
    })
})